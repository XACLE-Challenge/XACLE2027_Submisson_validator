#!/usr/bin/env python3
"""
Utility to validate the XACLE submission package.

Given a zip, directory, or YAML/CSV pair, the script ensures required
YAML fields are filled, the label/abbreviation formats are correct,
and the CSV lists 13500.wav–17499.wav with non-empty scores.
"""

from __future__ import annotations

import argparse
import csv
import io
import pathlib
import re
import sys
from typing import Any, List, Sequence, Set
from zipfile import ZipFile

try:
    import yaml
except ModuleNotFoundError as exc:
    print(
        "Missing dependency 'PyYAML'. Please install it with "
        "`python3 -m pip install pyyaml` and rerun this script.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


NULL_SENTINEL = "__XACLE_EXPLICIT_NULL__"
LABEL_PATTERN = re.compile(r"^[^_]+_[^_]+_[^_]+$")
MAX_ABBREVIATION_LENGTH = 10
EXPECTED_WAV_FILES = [f"{idx}.wav" for idx in range(13500, 17500)]


def format_path(parts: Sequence[str]) -> str:
    """Return display-friendly dot path."""
    result = ""
    for part in parts:
        if part.startswith("["):
            result += part
        elif not result:
            result = part
        else:
            result += f".{part}"
    return result


def last_key(parts: Sequence[str]) -> str | None:
    """Return the last non-index key name in the path."""
    for part in reversed(parts):
        if part.startswith("["):
            continue
        return part
    return None


def is_optional(parts: Sequence[str], optional_keys: Set[str]) -> bool:
    """Check if current path is allowed to stay empty."""
    key = last_key(parts)
    if key is None:
        return False
    normalized = key.strip()
    if "optional" in normalized.lower():
        return True
    # Normalize internal spacing to match keys recorded from comments.
    normalized = " ".join(normalized.split())
    return normalized in optional_keys


def iter_missing_entries(
    node: Any, path_parts: Sequence[str], optional_keys: Set[str]
) -> List[str]:
    """Return dotted paths of entries that evaluate to missing."""
    missing: List[str] = []
    if node is None:
        if not is_optional(path_parts, optional_keys):
            missing.append(format_path(path_parts))
        return missing

    if isinstance(node, dict):
        for key, value in node.items():
            missing.extend(
                iter_missing_entries(value, (*path_parts, str(key)), optional_keys)
            )
        return missing

    if isinstance(node, list):
        for idx, value in enumerate(node):
            missing.extend(
                iter_missing_entries(value, (*path_parts, f"[{idx}]"), optional_keys)
            )
        return missing

    if isinstance(node, str) and node == NULL_SENTINEL:
        return missing

    if isinstance(node, str) and not node.strip():
        if not is_optional(path_parts, optional_keys):
            missing.append(format_path(path_parts))

    return missing


def extract_optional_keys(raw_text: str) -> Set[str]:
    """Collect keys annotated as optional in the YAML comments."""
    keys: Set[str] = set()
    for line in raw_text.splitlines():
        if "#" not in line:
            continue
        code, comment = line.split("#", 1)
        if "optional" not in comment.lower():
            continue
        if ":" not in code:
            continue
        key = code.split(":", 1)[0].strip()
        if not key:
            continue
        key = key.lstrip("-").strip()
        if not key:
            continue
        keys.add(" ".join(key.split()))
    return keys


def _is_macos_artifact(path: pathlib.PurePosixPath) -> bool:
    return "__macosx" in (part.lower() for part in path.parts) or path.name.startswith(
        "._"
    )


def collect_zip_entries(names: List[str], extension: str, description: str) -> dict:
    entries: dict[str, str] = {}
    for name in names:
        if name.endswith("/"):
            continue
        path = pathlib.PurePosixPath(name)
        if _is_macos_artifact(path):
            continue
        if not path.name.lower().endswith(extension):
            continue
        stem = path.stem
        if stem in entries:
            raise ValueError(
                f"Duplicate {description} '{stem}' found in the zip archive."
            )
        entries[stem] = name
    return entries


def collect_directory_entries(directory: pathlib.Path, extension: str) -> dict:
    entries: dict[str, pathlib.Path] = {}
    for file in directory.rglob(f"*{extension}"):
        if not file.is_file():
            continue
        if file.name.startswith("._"):
            continue
        if not file.name.lower().endswith(extension):
            continue
        stem = file.stem
        if stem in entries:
            raise ValueError(
                f"Duplicate {extension} file with stem '{stem}' found in {directory}."
            )
        entries[stem] = file
    return entries


def pair_submission_files(
    yaml_map: dict, csv_map: dict, source_desc: str
) -> List[tuple[str, Any, Any]]:
    if not yaml_map:
        raise FileNotFoundError(f"No YAML files found in the {source_desc}.")
    if not csv_map:
        raise FileNotFoundError(f"No CSV files found in the {source_desc}.")

    missing_csv = sorted(set(yaml_map) - set(csv_map))
    missing_yaml = sorted(set(csv_map) - set(yaml_map))
    if missing_csv or missing_yaml:
        messages = []
        if missing_csv:
            messages.append(
                f"Missing CSV files for: {', '.join(missing_csv[:5])}"
                f"{'...' if len(missing_csv) > 5 else ''}"
            )
        if missing_yaml:
            messages.append(
                f"Missing YAML files for: {', '.join(missing_yaml[:5])}"
                f"{'...' if len(missing_yaml) > 5 else ''}"
            )
        raise ValueError("; ".join(messages))

    pairs: List[tuple[str, Any, Any]] = []
    for stem in sorted(yaml_map):
        pairs.append((stem, yaml_map[stem], csv_map[stem]))
    return pairs


def load_from_zip(zip_path: pathlib.Path) -> List[tuple[str, str, str]]:
    with ZipFile(zip_path) as archive:
        names = archive.namelist()
        yaml_map = collect_zip_entries(names, ".yaml", "YAML")
        csv_map = collect_zip_entries(names, ".csv", "CSV")
        entries = []
        for stem, yaml_name, csv_name in pair_submission_files(
            yaml_map, csv_map, "zip archive"
        ):
            yaml_text = archive.read(yaml_name).decode("utf-8")
            csv_text = archive.read(csv_name).decode("utf-8")
            entries.append((stem, yaml_text, csv_text))
    return entries


def load_from_directory(directory: pathlib.Path) -> List[tuple[str, str, str]]:
    yaml_map = collect_directory_entries(directory, ".yaml")
    csv_map = collect_directory_entries(directory, ".csv")
    entries = []
    for stem, yaml_path, csv_path in pair_submission_files(
        yaml_map, csv_map, "directory"
    ):
        entries.append(
            (
                stem,
                pathlib.Path(yaml_path).read_text(encoding="utf-8"),
                pathlib.Path(csv_path).read_text(encoding="utf-8"),
            )
        )
    return entries


def load_from_yaml_file(
    yaml_path: pathlib.Path, csv_path: pathlib.Path | None
) -> List[tuple[str, str, str]]:
    if csv_path is None:
        candidate = yaml_path.with_suffix(".csv")
        if candidate.exists():
            csv_path = candidate
        else:
            raise FileNotFoundError(
                "CSV file not provided. Use --csv to specify the CSV path."
            )
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    return [
        (
            yaml_path.stem,
            yaml_path.read_text(encoding="utf-8"),
            csv_path.read_text(encoding="utf-8"),
        )
    ]


def load_submission_files(
    path: pathlib.Path, csv_path: pathlib.Path | None
) -> List[tuple[str, str, str]]:
    if path.suffix.lower() == ".zip":
        return load_from_zip(path)
    if path.is_dir():
        return load_from_directory(path)
    if path.suffix.lower() == ".yaml":
        return load_from_yaml_file(path, csv_path)
    raise ValueError("Provide a .zip archive, directory, or YAML file.")


def validate_label(content: Any) -> bool:
    """Ensure submission.label follows the three-part underscore format."""
    if not isinstance(content, dict):
        return True
    submission = content.get("submission")
    if not isinstance(submission, dict):
        return True
    label = submission.get("label")
    if label is None:
        return True  # Missing label is handled by the missing-field check.
    if isinstance(label, str) and LABEL_PATTERN.fullmatch(label):
        return True
    print(
        "Error: submission.label must consist of three parts separated by underscores "
        '(e.g., "Okamoto_U-Tokyo_1").',
        file=sys.stderr,
    )
    return False


def validate_abbreviation(content: Any) -> bool:
    """Ensure submission.abbreviation does not exceed the length limit."""
    if not isinstance(content, dict):
        return True
    submission = content.get("submission")
    if not isinstance(submission, dict):
        return True
    abbreviation = submission.get("abbreviation")
    if abbreviation is None:
        return True
    if (
        isinstance(abbreviation, str)
        and len(abbreviation.strip()) <= MAX_ABBREVIATION_LENGTH
    ):
        return True
    print(
        f"Error: submission.abbreviation must be <= {MAX_ABBREVIATION_LENGTH} characters.",
        file=sys.stderr,
    )
    return False


def normalize_cell(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\ufeff", "").strip()


def row_has_content(row: Sequence[str]) -> bool:
    return any(normalize_cell(cell) for cell in row)


def validate_csv_contents(csv_text: str) -> bool:
    """Ensure the CSV lists wav files from 13500-17499 with non-empty scores."""
    reader = csv.reader(io.StringIO(csv_text))
    rows: List[tuple[int, List[str]]] = []
    for row in reader:
        rows.append((reader.line_num, row))

    if not rows:
        print("Error: CSV file is empty.", file=sys.stderr)
        return False

    first_data_index = 0
    while first_data_index < len(rows) and not row_has_content(
        rows[first_data_index][1]
    ):
        first_data_index += 1

    if first_data_index >= len(rows):
        print("Error: CSV file contains only blank rows.", file=sys.stderr)
        return False

    _, header_row = rows[first_data_index]
    data_rows = rows[first_data_index + 1 :]
    first_header_cell = normalize_cell(header_row[0]) if header_row else ""

    if first_header_cell.lower() != "wav_file_name":
        data_rows = rows[first_data_index:]
    elif not data_rows:
        print("Error: CSV file must contain data rows.", file=sys.stderr)
        return False

    issues: List[str] = []
    actual_files: List[tuple[int, str]] = []
    for idx, (line_no, row) in enumerate(data_rows, start=1):
        first_value = normalize_cell(row[0]) if len(row) >= 1 else ""
        actual_files.append((line_no, first_value))
        if not first_value:
            issues.append(
                f"Line {line_no}: first column is empty (expected 13500.wav-17499.wav)."
            )

        second_value = normalize_cell(row[1]) if len(row) >= 2 else ""
        if not second_value:
            issues.append(
                f"Line {line_no}: second column is empty; a score is required."
            )

    expected_len = len(EXPECTED_WAV_FILES)
    if len(actual_files) != expected_len:
        issues.append(
            f"CSV must contain {expected_len} entries (13500.wav-17499.wav); "
            f"found {len(actual_files)} data rows."
        )

    expected_set = set(EXPECTED_WAV_FILES)
    lines_by_name: dict[str, List[int]] = {}
    for line_no, name in actual_files:
        lines_by_name.setdefault(name, []).append(line_no)

    missing_names = [name for name in EXPECTED_WAV_FILES if name not in lines_by_name]
    if missing_names:
        sample = ", ".join(missing_names[:5])
        ellipsis = "..." if len(missing_names) > 5 else ""
        issues.append(f"Missing entries for: {sample}{ellipsis}.")

    extra_entries = [
        (name, line_nos)
        for name, line_nos in lines_by_name.items()
        if name not in expected_set
    ]
    for name, line_nos in extra_entries[:5]:
        issues.append(
            f"Line {line_nos[0]}: unexpected entry '{name}' "
            "is outside 13500.wav-17499.wav."
        )
    if len(extra_entries) > 5:
        issues.append(f"... plus {len(extra_entries) - 5} more unexpected entries.")

    duplicate_entries = [
        (name, line_nos)
        for name, line_nos in lines_by_name.items()
        if len(line_nos) > 1 and name in expected_set
    ]
    for name, line_nos in duplicate_entries[:5]:
        joined = ", ".join(str(num) for num in line_nos)
        issues.append(f"Entries for '{name}' appear multiple times (lines {joined}).")
    if len(duplicate_entries) > 5:
        issues.append(f"... plus {len(duplicate_entries) - 5} more duplicated entries.")

    if issues:
        print("CSV validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return False
    return True


def validate_submission(yaml_text: str, csv_text: str) -> bool:
    success = True
    try:
        optional_keys = extract_optional_keys(yaml_text)
        sanitized_text = yaml_text.replace("!!null", NULL_SENTINEL)
        content = yaml.safe_load(sanitized_text)
    except yaml.YAMLError as exc:
        print(f"Failed to parse YAML: {exc}", file=sys.stderr)
        return False

    if not validate_label(content):
        success = False
    if not validate_abbreviation(content):
        success = False

    missing = iter_missing_entries(content, (), optional_keys)
    if not missing:
        print("All fields are filled.")
    else:
        print("Missing or empty entries:")
        for entry in missing:
            print(entry)
        success = False

    if validate_csv_contents(csv_text):
        print("CSV validation passed.")
    else:
        success = False

    return success


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for missing fields in the submission YAML file."
    )
    parser.add_argument(
        "input_path",
        type=pathlib.Path,
        help="Path to the submission zip file, directory, or YAML file.",
    )
    parser.add_argument(
        "--csv",
        type=pathlib.Path,
        help="Path to the CSV file (required when checking a standalone YAML file).",
    )
    args = parser.parse_args()

    try:
        submissions = load_submission_files(args.input_path, args.csv)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    overall_success = True
    for stem, yaml_text, csv_text in submissions:
        print(f"=== Validating {stem} ===")
        if not validate_submission(yaml_text, csv_text):
            overall_success = False
        print()

    return 0 if overall_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
