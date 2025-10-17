# Unified Site Snapshot

Create a clean, offline version of any web page with one HTML, one CSS, and one JS file.

> ⚠️ Use this tool **only if you have rights or permission** to copy the site. Respect copyright, Terms of Service, and robots.txt.

---

## Quickstart

```bash
pip install -r requirements.txt
python unified_site_snapshot.py https://example.com -o ./snapshot
# or crawl mode:
python unified_site_snapshot.py crawl https://example.com -o ./snapshot
```

Open `snapshot/index.html` to view offline.

---

## Output structure

```
snapshot/
  assets/
    css/styles.css
    js/main.js
    media/
      favicon/
      uploads/images/
  index.html
```

* Inline `<style>` / `<script>` order preserved (before → prepend, after → append)
* All assets (images, CSS, JS, icons) are downloaded and linked locally
* Exactly **1 HTML**, **1 CSS**, and **1 JS** file

---

## Requirements

```
requests
beautifulsoup4
lxml
```

---

### Legal note

Use for licensed, personal, or archival purposes only. Do **not** download or redistribute websites in violation of their terms.
