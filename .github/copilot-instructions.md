<!-- Auto-generated guidance for AI coding agents. Update only with repository knowledge. -->
# Copilot instructions for BerichtGeneratorX

Purpose
- Help AI agents make safe, focused changes in the BerichtGeneratorX codebase.

Quick overview
- Entry points: `python main.py` (Tkinter GUI) and `python main_qt.py` (PySide6/qtui modern UI). `UITest.py` is a PySide6 UI lab.
- Main GUI logic lives in `gui_main.py`/`qtui/` (heavy UI code). Business logic lives in `core_*.py` (e.g. `core_ocr.py`, `core_kurzel.py`).

Essential patterns and APIs
- Central configuration: `config_manager.CentralConfigManager` / `config_manager.config_file` (file: `GearBoxExiff.json`). Always preserve JSON schema and migration helpers (`_migrate_config`).
- EXIF metadata: `utils_exif.get_exif_usercomment`, `read_metadata`, `write_metadata`, `update_metadata`. EXIF JSON is stored in the JPEG/TIFF UserComment tag with an ASCII prefix. Use these helpers (do not manually manipulate EXIF bytes).
- OCR: `core_ocr.get_reader()` returns the singleton EasyOCR reader. Use `run_ocr_easyocr()` or `find_text_box_easyocr()` for recognition. The reader is intentionally global for performance.
- Logging: use `utils_logging.get_logger(name, extra)` and `write_detailed_log()`; many modules expect structured `extra` payloads.

Data flow (common):
- Image file (from `01_Fotos/`) → EXIF read (`utils_exif.read_metadata`) → OCR (`core_ocr.run_ocr_easyocr`) → evaluation stored to EXIF (`utils_exif.set_evaluation`) or exported via CSV (`utils_csv`).

Conventions to follow
- Singletons: prefer using provided singletons (config manager, easyocr reader) instead of creating ad-hoc instances.
- EXIF compatibility is critical: use `utils_exif` helpers to read/write JSON in UserComment. Keep the ASCII prefix and JSON structure.
- Settings read path: UI code frequently uses a settings manager (e.g., `qtui.settings_manager.get_settings_manager()`), or `CentralConfigManager` for app-wide defaults.
- Logging calls use semantic event names (e.g. `log_ocr.info("ocr_raw_text", extra={...})`). Preserve those keys when adding instrumentation.

Files & directories to reference when making changes
- `main.py`, `main_qt.py`, `UITest.py` — application entry points.
- `gui_main.py`, `gui_components.py`, `gui_dialogs.py`, `qtui/` — UI-heavy code; prefer small, incremental UI changes.
- `core_ocr.py`, `core_kurzel.py` — core processing logic.
- `config_manager.py` — canonical config schema and migration.
- `utils_exif.py`, `utils_csv.py`, `utils_helpers.py`, `utils_logging.py` — shared utilities.

Build & run notes (discoverable commands)
- Run the main (Tkinter): `python main.py`
- Run the Qt app: `python main_qt.py` (uses `qtui` package and PySide6)
- Run UI testbed: `python UITest.py`
- Dependencies visible via imports: `PySide6`, `easyocr`, `cv2` (opencv-python), `Pillow`, `numpy`. Create a virtualenv and install these before running the Qt UI.

Quick examples (copyable patterns)
- Read metadata:
  from utils_exif import read_metadata
  md = read_metadata(path_to_image)  # returns dict or {}
- Save OCR info into EXIF:
  from utils_exif import set_ocr_info
  set_ocr_info(path, tag='HSS', confidence=0.92, box=(10,20,50,30))
- Get global OCR reader:
  from core_ocr import get_reader
  reader = get_reader()  # singleton EasyOCR Reader

When to be cautious
- Do not change EXIF format: backward compatibility with existing images is required.
- `gui_main.py` is large — prefer refactors that add small modules rather than editing huge blocks in-place.
- Performance-sensitive code (thumbnail caches, OCR reader) uses global caches/singletons. Be careful to avoid reinitializing them.

If you need more context
- `MODULE_STRUCTURE.md` contains a high-level overview and recommended split points for refactoring.
- Search for `get_logger('app', ...)` and `write_detailed_log` to find areas with structured logging expectations.

Next step for reviewers
- Please review this file for missing APIs or any additional constraints (especially around EXIF schema and config migrations). Report gaps and I'll iterate.
