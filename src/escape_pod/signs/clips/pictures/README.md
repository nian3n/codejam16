# Still pictures for the glossary

The glossary shows a looping PopSign clip for each word. PopSign has no clips for the digits 0–9. The digits are still hand shapes, so a picture is enough.

## Add a picture

1. Find a picture that you may reuse. Look for a free license: public domain, CC0, CC BY or CC BY-SA. Wikimedia Commons is a good place to look. In Google Images, use **Tools → Usage rights → Creative Commons licenses**.
2. Make sure that the picture shows the ASL digit, not the digit of another sign language.
3. Save it in this folder as `<digit>.png`, `.jpg` or `.webp`, for example `7.png`.
4. Add an entry to `index.json`:

```json
{
  "pictures": {
    "7": {
      "file": "7.png",
      "author": "Jane Doe",
      "license": "CC BY-SA 4.0",
      "source": "https://commons.wikimedia.org/wiki/File:..."
    }
  }
}
```

5. Run `uv run pytest tests/test_signs.py`. The test checks that each file exists and that each entry has a license and a source.

The glossary shows the author, the license and the source under each picture. Most free licenses require that credit.

Do not use a picture with no license, or one that says "all rights reserved".
