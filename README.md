# XACLE Challenge 2027 Submission Checker

`check.py` validates one or more XACLE Challenge 2027 submission packages from a ZIP archive, directory, or standalone YAML/CSV pair. When multiple YAML/CSV pairs are present, each submission is checked in turn. The script verifies:

- All required YAML fields are filled (`!!null` is allowed, and fields marked “optional” may remain blank)
- `submission.label` follows the three-part `Lastname_InstitutionAbbrev_Index` format
- `submission.abbreviation` is at most 10 characters long
- The CSV lists every file from `13500.wav` to `17499.wav`, each with a non-empty score in the second column

## Setup

1. Create and activate any Python 3.11+ environment (Conda, venv, etc.).
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

```bash
python check.py <zip/dir/YAML> [--csv path/to/csv]
```

- When given a ZIP or directory, the script automatically locates all matching YAML/CSV pairs inside it and validates each submission sequentially.
- When given only a YAML file, the script looks for a sibling `.csv` with the same base name. Use `--csv` to point to a different CSV file if needed.

### Example

```bash
python check.py Okamoto_U-Tokyo_1.zip
```

### Expected ZIP Layout

A valid ZIP can contain one or more submissions. Each submission should provide matching YAML/CSV pairs. Example:

```
Okamoto_UTokyo.zip
├── Okamoto_UTokyo_1.csv
├── Okamoto_UTokyo_1.yaml
└── Okamoto_UTokyo.pdf
```

Files inside nested folders are also supported as long as each `.yaml` has a `.csv` with the same base name.

The output reports both YAML and CSV validation results. If the package is valid, it prints `All fields are filled.` followed by `CSV validation passed.`.

## Output Details

- Missing YAML fields are printed as dotted paths.
- Invalid `submission.label` or `submission.abbreviation` values trigger clear error messages.
- CSV validation pinpoints line numbers for empty columns, missing file names, duplicates, or out-of-range entries.
