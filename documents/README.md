# Documents folder

Put the educational documents you want the chatbot to answer questions from in this folder.

- Supported formats: `.pdf`, `.txt`, `.md`
- `README.md` (this file) is ignored automatically
- Text-based PDFs work. Scanned PDFs (images of pages) need OCR first
- After adding, removing, or changing a file, the index is rebuilt automatically on the next
  Document Q&A question. You can also force it with `POST /document/reindex`

Only add documents you have the right to use. Good sources: your own notes, public-domain material,
or guides that explicitly allow reuse. Do not commit copyrighted PDFs to a public GitHub repository.

`sample_wellbeing_guide.txt` is an original example so the feature works out of the box.
