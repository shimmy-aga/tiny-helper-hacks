// Duplicate template, replace matching Smart Objects (by NAME), fit INSIDE (width & height), save PNG.
// 2025, use at your own risk.
#target photoshop

(function () {
    if (app.documents.length === 0) { alert("No open document."); return; }

    var baseDoc = app.activeDocument;
    var baseName = baseDoc.name.match(/(.*)\.[^\.]+$/)[1];

    // ===== CONFIG ============================================================
    // Match SOs whose name contains this string or matches this RegExp.
    var NAME_FILTER = /design/i;
    var EXPORT_MAX_LONG = 3000;   // final export: max long edge in px
    var RESAMPLE = ResampleMethod.BICUBICSHARPER; // good for downscaling
    // ========================================================================

    // PNG (Save for Web) Options
    var pngOpts = new ExportOptionsSaveForWeb();
    pngOpts.format = SaveDocumentType.PNG; pngOpts.PNG8 = false;
    pngOpts.transparency = true; pngOpts.interlaced = false; pngOpts.quality = 100;

    // Pick replacement files
    var files = ($.os.search(/windows/i) !== -1)
      ? File.openDialog("Select logo/image files", "*.psd;*.tif;*.tiff;*.jpg;*.jpeg;*.png;*.eps", true)
      : File.openDialog("Select logo/image files", fileFilterMac, true);
    if (!files || !files.length) return;

    // Choose save folder ONCE
    var saveFolder = Folder.selectDialog("Choose save folder");
    if (!saveFolder) return;

    // Work in pixels (restore later)
    var originalRuler = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;

    for (var f = 0; f < files.length; f++) {
        var file = files[f];
        var nameStem = file.name.match(/(.*)\.[^\.]+$/)[1];

        try {
            var workDoc = baseDoc.duplicate(baseName + "_" + nameStem, false);
            app.activeDocument = workDoc;

            // Collect Smart Objects that match by NAME
            var soLayers = [];
            collectSmartObjects(workDoc, soLayers, nameMatcherFactory(NAME_FILTER));

            if (!soLayers.length) {
                alert("No matching Smart Object layers by NAME for: " + nameStem);
                workDoc.close(SaveOptions.DONOTSAVECHANGES);
                continue;
            }

            // Cache original bounds (width & height) per matching layer
            var targetW = [], targetH = [];
            for (var i = 0; i < soLayers.length; i++) {
                var b = soLayers[i].bounds;
                var w = (b[2].value - b[0].value);
                var h = (b[3].value - b[1].value);
                targetW[i] = (w > 0) ? w : 1;
                targetH[i] = (h > 0) ? h : 1;
            }

            // Replace & FIT-INSIDE (by whichever dimension limits)
            for (var s = 0; s < soLayers.length; s++) {
                var lyr = soLayers[s];
                replaceContents(file, lyr);

                // Measure new content bounds
                var nb = lyr.bounds;
                var newW = (nb[2].value - nb[0].value); if (newW <= 0) newW = 1;
                var newH = (nb[3].value - nb[1].value); if (newH <= 0) newH = 1;

                // Compute scale to fit inside original box (no overflow)
                var scaleW = targetW[s] / newW;
                var scaleH = targetH[s] / newH;
                var scalePct = Math.min(scaleW, scaleH) * 100.0;

                // Apply uniform scale, centered
                lyr.resize(scalePct, scalePct, AnchorPosition.MIDDLECENTER);
            }

            // Downsize whole document to target long edge (optional)
            var wPx = workDoc.width.as('px');
            var hPx = workDoc.height.as('px');
            var longEdge = Math.max(wPx, hPx);
            if (longEdge > EXPORT_MAX_LONG) {
                var scale = EXPORT_MAX_LONG / longEdge;
                var newWdoc = Math.max(1, Math.round(wPx * scale));
                var newHdoc = Math.max(1, Math.round(hPx * scale));
                workDoc.resizeImage(UnitValue(newWdoc, 'px'), UnitValue(newHdoc, 'px'), null, RESAMPLE);
            }

            // Export PNG (Save for Web) to chosen folder
            var pngFile = new File(saveFolder + "/" + baseName + "_" + nameStem + ".png");
            workDoc.exportDocument(pngFile, ExportType.SAVEFORWEB, pngOpts);

            workDoc.close(SaveOptions.DONOTSAVECHANGES);

        } catch (e) {
            alert("Error creating mockup for: " + file.fsName + "\n\n" + e);
            try { if (app.activeDocument !== baseDoc) app.activeDocument.close(SaveOptions.DONOTSAVECHANGES); } catch (ee) {}
        }
    }

    app.activeDocument = baseDoc;
    app.preferences.rulerUnits = originalRuler;

    alert("✅ Done! Created " + files.length + " mockup(s) (PNG).");

    // ---------- Helpers ----------
    function collectSmartObjects(container, outArr, matcher) {
        // ArtLayers
        for (var i = 0; i < container.artLayers.length; i++) {
            var lyr = container.artLayers[i];
            try {
                if (lyr.kind === LayerKind.SMARTOBJECT && (!matcher || matcher(lyr))) {
                    outArr.push(lyr);
                }
            } catch (e) {}
        }
        // Recurse groups
        for (var g = 0; g < container.layerSets.length; g++) {
            collectSmartObjects(container.layerSets[g], outArr, matcher);
        }
    }

    function nameMatcherFactory(filter) {
        if (!filter) return null;
        if (filter instanceof RegExp) return function (lyr) { return filter.test(lyr.name); };
        var s = String(filter).toLowerCase();
        return function (lyr) { return lyr.name && lyr.name.toLowerCase().indexOf(s) !== -1; };
    }

    function fileFilterMac(f) {
        if (f.constructor.name === "Folder" ||
            f.name.match(/\.(psd|tif|tiff|jpg|jpeg|png|eps)$/i) != null) { return true; }
        return false;
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
})();
