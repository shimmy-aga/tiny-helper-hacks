/** 
 * Headless batch: duplicate template(s), replace matching Smart Objects (by NAME),
 * fit INSIDE (width & height), export PNG/JPG/PSD as configured.
 * 2025 — use at your own risk.
 */
#target photoshop
app.displayDialogs = DialogModes.NO;

try {
(function () {
    // -------- JSON.parse fallback for older ExtendScript --------
    function safeJSONParse(s) {
        if (!s) throw new Error("Empty config.");
        // strip BOM
        if (s.charCodeAt && s.charCodeAt(0) === 0xFEFF) s = s.slice(1);
        // tolerate comments & trailing commas just in case
        s = s.replace(/^\s*\/\/.*$/mg, "")     // // line comments
             .replace(/\/\*[\s\S]*?\*\//g, "") // /* block comments */
             .replace(/,\s*([}\]])/g, "$1");   // trailing commas
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(s);
        return (new Function("return (" + s + ");"))(); // last resort
    }

    // -------- utilities --------
    function readTextFile(f){ f.encoding="UTF8"; if(!f.exists) throw new Error("Missing file: " + f.fsName); f.open('r'); var s=f.read(); f.close(); return s; }
    function numOr(v,d){ v=Number(v); return isNaN(v)?d:v; }
    function stem(name){ var m=name.match(/(.*)\.[^\.]+$/); return m?m[1]:name; }
    function listFiles(folder, regex){
        var out=[], arr=folder.getFiles(function(x){ return !(x instanceof Folder) && regex.test(x.name); });
        for(var i=0;i<arr.length;i++) out.push(arr[i]); return out;
    }
    function toRegExp(value, def){
        if (value == null) return def;
        if (value instanceof RegExp) return value;
        var m = String(value).match(/^\/(.+)\/([gimuy]*)$/);
        if (m) return new RegExp(m[1], m[2]);
        return new RegExp(String(value), "i");
    }
    function makeLogger(file){
        return function(msg){
            try { file.encoding="UTF8"; file.open(file.exists?'a':'w'); file.writeln(msg); file.close(); } catch(e){}
        };
    }

    function collectSmartObjects(container, outArr, matcher) {
        try {
            for (var i=0;i<container.artLayers.length;i++){
                var lyr = container.artLayers[i];
                try { if (lyr.kind === LayerKind.SMARTOBJECT && (!matcher || matcher(lyr))) outArr.push(lyr); } catch(e){}
            }
            for (var g=0; g<container.layerSets.length; g++) collectSmartObjects(container.layerSets[g], outArr, matcher);
        } catch(e){}
    }
    function nameMatcherFactory(filter) {
        if (!filter) return null;
        if (filter instanceof RegExp) return function (lyr) { return filter.test(lyr.name); };
        var s = String(filter).toLowerCase();
        return function (lyr) { return lyr.name && lyr.name.toLowerCase().indexOf(s) !== -1; };
    }
    function replaceContents(newFile, theLayer) {
        app.activeDocument.activeLayer = theLayer;
        var id = stringIDToTypeID("placedLayerReplaceContents");
        var d = new ActionDescriptor();
        d.putPath(charIDToTypeID("null"), new File(newFile));
        d.putInteger(charIDToTypeID("PgNm"), 1);
        executeAction(id, d, DialogModes.NO);
        return app.activeDocument.activeLayer;
    }
    function exportPNG(doc, outFile){
        var opts = new ExportOptionsSaveForWeb();
        opts.format = SaveDocumentType.PNG; opts.PNG8 = false;
        opts.transparency = true; opts.interlaced = false; opts.quality = 100;
        doc.exportDocument(outFile, ExportType.SAVEFORWEB, opts);
    }
    function exportJPG(doc, outFile, quality){
        var opts = new JPEGSaveOptions();
        opts.quality = Math.min(12, Math.max(0, Number(quality||10)));
        opts.embedColorProfile = true; opts.matte = MatteType.NONE;
        doc.saveAs(outFile, opts, true, Extension.LOWERCASE);
    }
    function savePSD(doc, outFile){
        var opts = new PhotoshopSaveOptions();
        opts.layers = true; opts.embedColorProfile = true; opts.maximizeCompatibility = true;
        doc.saveAs(outFile, opts, true, Extension.LOWERCASE);
    }

    // -------- load config (next to this JSX or ~/batch_config.json) --------
    var THIS_FILE = File($.fileName);
    var CONFIG_CANDIDATES = [
        File(THIS_FILE.path + "/config.json"),
        File(Folder("~").fsName + "/batch_config.json")
    ];
    function loadConfig(cands){
        for (var i=0;i<cands.length;i++){
            var f=cands[i];
            if (f && f.exists){
                var s = readTextFile(f);
                try { var obj = safeJSONParse(s); obj.__cfgPath = f.fsName; return obj; }
                catch(e){ throw new Error("Invalid JSON in " + f.fsName + ": " + e); }
            }
        }
        throw new Error("config.json not found next to script or in home folder.");
    }
    var cfg = loadConfig(CONFIG_CANDIDATES);

    // -------- support relative paths (relative to this JSX) --------
    var BASE_PATH = THIS_FILE.path;
    function resolveFolder(pathStr) {
        if (!pathStr) return null;
        var f = Folder(pathStr);
        if (!f.exists) f = Folder(BASE_PATH + "/" + pathStr);
        return f;
    }

    // ===== CONFIG with defaults & validation =====
    var NAME_FILTER         = toRegExp(cfg.nameFilter, /design/i);   // match SO layer names
    var EXPORT_MAX_LONG     = numOr(cfg.exportMaxLong, 3000);        // px
    var RESAMPLE            = ResampleMethod.BICUBICSHARPER;

    var BASES_DIR           = cfg.basesDir ? resolveFolder(cfg.basesDir) : null;
    var LOGOS_DIR           = cfg.logosDir ? resolveFolder(cfg.logosDir) : null;
    var OUTPUT_DIR          = cfg.outputDir ? resolveFolder(cfg.outputDir) : null;
    var USE_ACTIVE_DOC      = !!cfg.useActiveDocument;
    var MAKE_SUBFOLDERS     = cfg.makeSubfolders !== false;
    var OVERWRITE           = !!cfg.overwrite;
    var EXPORT_FORMATS      = (cfg.formats && cfg.formats.length) ? cfg.formats : ["png"];
    var jpgQuality          = Math.min(12, Math.max(0, Number(cfg.jpgQuality || 10)));

    if (!LOGOS_DIR || !LOGOS_DIR.exists) throw new Error("logosDir missing or not found: " + (LOGOS_DIR ? LOGOS_DIR.fsName : cfg.logosDir));
    if (!OUTPUT_DIR) throw new Error("outputDir missing.");
    if (!OUTPUT_DIR.exists) OUTPUT_DIR.create();
    if (!USE_ACTIVE_DOC && (!BASES_DIR || !BASES_DIR.exists)) throw new Error("Either set useActiveDocument=true or provide a valid basesDir.");
    if (USE_ACTIVE_DOC && app.documents.length === 0) throw new Error("useActiveDocument=true but no document is open.");

    // -------- logging --------
    var logFile = File(OUTPUT_DIR.fsName + "/batch_log.txt");
    var logger = makeLogger(logFile);
    logger("=== Batch start: " + new Date().toUTCString() + " ===");
    logger("Config: " + (cfg.__cfgPath || "inline") );
    logger("BASES_DIR=" + (BASES_DIR?BASES_DIR.fsName:"(active)"));
    logger("LOGOS_DIR=" + LOGOS_DIR.fsName);
    logger("OUTPUT_DIR=" + OUTPUT_DIR.fsName);

    // -------- collect files --------
    var logoFiles = listFiles(LOGOS_DIR, /\.(psd|psb|tif|tiff|jpg|jpeg|png|eps)$/i);
    if (!logoFiles.length) throw new Error("No logo files found in " + LOGOS_DIR.fsName);

    var baseDocs = [];
    if (USE_ACTIVE_DOC) {
        baseDocs.push({ kind: "active", name: app.activeDocument.name, openFn: function(){ return app.activeDocument; }});
    } else {
        var baseFiles = listFiles(BASES_DIR, /\.(psd|psb)$/i);
        if (!baseFiles.length) throw new Error("No PSD/PSB templates found in " + BASES_DIR.fsName);
        for (var b=0; b<baseFiles.length; b++) {
            (function(file){
                baseDocs.push({ kind:"file", name:file.name, openFn:function(){ return app.open(file); } });
            })(baseFiles[b]);
        }
    }

    // -------- run --------
    var originalRuler = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;

    var totalExports = 0;

    for (var bi=0; bi<baseDocs.length; bi++) {
        var baseItem = baseDocs[bi];
        var baseDoc = baseItem.openFn();
        var baseName = stem(baseDoc.name);
        logger("Template: " + baseName);

        for (var li=0; li<logoFiles.length; li++) {
            var logo = logoFiles[li];
            var logoStem = stem(logo.name);

            try {
                var workName = baseName + "_" + logoStem;
                var workDoc = baseDoc.duplicate(workName, false);
                app.activeDocument = workDoc;

                // collect matching SOs
                var soLayers = [];
                collectSmartObjects(workDoc, soLayers, nameMatcherFactory(NAME_FILTER));
                if (!soLayers.length) {
                    logger("  [WARN] No matching Smart Objects for NAME_FILTER=" + NAME_FILTER);
                    workDoc.close(SaveOptions.DONOTSAVECHANGES);
                    continue;
                }

                // cache target bounds
                var targetW = [], targetH = [];
                for (var i=0; i<soLayers.length; i++) {
                    var bds = soLayers[i].bounds;
                    targetW[i] = Math.max(1, bds[2].value - bds[0].value);
                    targetH[i] = Math.max(1, bds[3].value - bds[1].value);
                }

                // replace + fit inside
                for (var s=0; s<soLayers.length; s++) {
                    var lyr = soLayers[s];
                    replaceContents(logo, lyr);
                    var nb = lyr.bounds;
                    var newW = Math.max(1, nb[2].value - nb[0].value);
                    var newH = Math.max(1, nb[3].value - nb[1].value);
                    var scalePct = Math.min(targetW[s]/newW, targetH[s]/newH) * 100.0;
                    lyr.resize(scalePct, scalePct, AnchorPosition.MIDDLECENTER);
                }

                // resize document by long edge
                var wPx = workDoc.width.as('px'), hPx = workDoc.height.as('px');
                var longEdge = (wPx > hPx) ? wPx : hPx;
                if (longEdge > EXPORT_MAX_LONG) {
                    var sc = EXPORT_MAX_LONG / longEdge;
                    var newWdoc = Math.max(1, Math.round(wPx * sc));
                    var newHdoc = Math.max(1, Math.round(hPx * sc));
                    workDoc.resizeImage(UnitValue(newWdoc,'px'), UnitValue(newHdoc,'px'), null, RESAMPLE);
                }

                // output folder (optional per-template subfolder)
                var outFolder = OUTPUT_DIR;
                if (MAKE_SUBFOLDERS) {
                    outFolder = Folder(OUTPUT_DIR.fsName + "/" + baseName);
                    if (!outFolder.exists) outFolder.create();
                }

                // exports
                var exportedThis = 0;
                for (var ef=0; ef<EXPORT_FORMATS.length; ef++) {
                    var fmt = String(EXPORT_FORMATS[ef]).toLowerCase();
                    if (fmt === "png") {
                        var pngFile = File(outFolder.fsName + "/" + workName + ".png");
                        if (OVERWRITE || !pngFile.exists) exportPNG(workDoc, pngFile), exportedThis++;
                    } else if (fmt === "jpg" || fmt === "jpeg") {
                        var jpgFile = File(outFolder.fsName + "/" + workName + ".jpg");
                        if (OVERWRITE || !jpgFile.exists) exportJPG(workDoc, jpgFile, jpgQuality), exportedThis++;
                    } else if (fmt === "psd") {
                        var psdFile = File(outFolder.fsName + "/" + workName + ".psd");
                        if (OVERWRITE || !psdFile.exists) savePSD(workDoc, psdFile), exportedThis++;
                    } else {
                        logger("  [WARN] Unknown export format: " + fmt);
                    }
                }

                workDoc.close(SaveOptions.DONOTSAVECHANGES);
                totalExports += exportedThis;
                logger("  OK: " + workName + "  (" + exportedThis + " file(s))");

            } catch (e) {
                logger("  [ERROR] " + logo.fsName + " -> " + e);
                try { if (app.activeDocument !== baseDoc) app.activeDocument.close(SaveOptions.DONOTSAVECHANGES); } catch(ee){}
            }
        }

        if (baseItem.kind === "file") { try { baseDoc.close(SaveOptions.DONOTSAVECHANGES); } catch(e){} }
    }

    app.preferences.rulerUnits = originalRuler;
    logger("=== Done. Exported files: " + totalExports + " ===");
    // no alerts — automation-friendly
})();
}
catch (e) {
    alert("Batch script failed:\n" + e);
}