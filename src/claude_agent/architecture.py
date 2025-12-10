"""
Architecture File Validation
=============================

Validation functions for architecture lock files (contracts.yaml, schemas.yaml, decisions.yaml).
Ensures files contain valid YAML with required fields before coding sessions proceed.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from claude_agent.decisions import DecisionLoadError, load_decisions

# Module-level constants for architecture file paths
ARCH_DIR_NAME = "architecture"
CONTRACTS_FILE = "contracts.yaml"
SCHEMAS_FILE = "schemas.yaml"
DECISIONS_FILE = "decisions.yaml"
REQUIRED_FILES = [CONTRACTS_FILE, SCHEMAS_FILE, DECISIONS_FILE]


class ArchitectureValidationError(Exception):
    """Error validating architecture files."""

    def __init__(self, file_name: str, message: str):
        self.file_name = file_name
        self.message = message
        super().__init__(f"{file_name}: {message}")


@dataclass
class ContractEndpoint:
    """A single API endpoint in a contract."""

    path: str
    method: str


@dataclass
class Contract:
    """An API contract definition."""

    name: str
    endpoints: list[ContractEndpoint]
    description: str = ""


@dataclass
class SchemaField:
    """A field in a data schema."""

    name: str
    type: str
    constraints: list[str]


@dataclass
class Schema:
    """A data schema definition."""

    name: str
    fields: list[SchemaField]
    description: str = ""


def get_architecture_dir(project_dir: Path, specs_dir: str = "specs") -> Path:
    """
    Get canonical path to architecture directory for creating new files.

    The canonical location is {specs_dir}/architecture/ to keep architecture
    files co-located with other spec workflow files.

    Args:
        project_dir: Project directory
        specs_dir: Name of specs directory (default: "specs")

    Returns:
        Path to architecture directory (may not exist yet)
    """
    return project_dir / specs_dir / ARCH_DIR_NAME


def find_architecture_dir(project_dir: Path, specs_dir: str = "specs") -> Optional[Path]:
    """
    Find existing architecture directory, checking multiple locations.

    Search order (for backwards compatibility):
    1. {specs_dir}/architecture/ - Preferred canonical location
    2. architecture/ - Legacy project root location

    Args:
        project_dir: Project directory
        specs_dir: Name of specs directory (default: "specs")

    Returns:
        Path to architecture directory if found, None otherwise
    """
    # Check specs subdirectory first (preferred location)
    specs_arch_dir = project_dir / specs_dir / ARCH_DIR_NAME
    if specs_arch_dir.is_dir():
        return specs_arch_dir

    # Fall back to project root (legacy location)
    root_arch_dir = project_dir / ARCH_DIR_NAME
    if root_arch_dir.is_dir():
        return root_arch_dir

    return None


def _validate_yaml_list(
    file_path: Path,
    file_name: str,
    list_key: str,
    item_name: str = "item",
) -> list[dict]:
    """
    Load and validate YAML file containing a list of dicts.

    Common validation helper that:
    1. Loads YAML and verifies root is a dict
    2. Extracts the list field and verifies it's a list
    3. Verifies each item in the list is a dict

    Args:
        file_path: Path to the YAML file
        file_name: Human-readable name for error messages
        list_key: The key containing the list (e.g., "contracts", "schemas")
        item_name: Name for items in error messages (e.g., "contract", "schema")

    Returns:
        List of dicts from the YAML file

    Raises:
        ArchitectureValidationError: If validation fails
    """
    if not file_path.exists():
        return []

    try:
        with open(file_path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ArchitectureValidationError(
            file_name, f"Failed to parse YAML: {e}"
        ) from e

    if not isinstance(data, dict):
        raise ArchitectureValidationError(
            file_name, f"Invalid format: expected dict, got {type(data).__name__}"
        )

    items_list = data.get(list_key, [])
    if not isinstance(items_list, list):
        raise ArchitectureValidationError(
            file_name,
            f"Invalid '{list_key}' field: expected list, got {type(items_list).__name__}",
        )

    for i, item in enumerate(items_list):
        if not isinstance(item, dict):
            raise ArchitectureValidationError(
                file_name,
                f"Invalid {item_name} at index {i}: expected dict, got {type(item).__name__}",
            )

    return items_list


def get_contracts_path(project_dir: Path, specs_dir: str = "specs") -> Path:
    """Get canonical path to contracts file (for creating new files)."""
    return get_architecture_dir(project_dir, specs_dir) / CONTRACTS_FILE


def get_schemas_path(project_dir: Path, specs_dir: str = "specs") -> Path:
    """Get canonical path to schemas file (for creating new files)."""
    return get_architecture_dir(project_dir, specs_dir) / SCHEMAS_FILE


def find_contracts_path(project_dir: Path, specs_dir: str = "specs") -> Optional[Path]:
    """Find existing contracts file, checking multiple locations."""
    arch_dir = find_architecture_dir(project_dir, specs_dir)
    if arch_dir is None:
        return None
    contracts_path = arch_dir / CONTRACTS_FILE
    return contracts_path if contracts_path.exists() else None


def find_schemas_path(project_dir: Path, specs_dir: str = "specs") -> Optional[Path]:
    """Find existing schemas file, checking multiple locations."""
    arch_dir = find_architecture_dir(project_dir, specs_dir)
    if arch_dir is None:
        return None
    schemas_path = arch_dir / SCHEMAS_FILE
    return schemas_path if schemas_path.exists() else None


def load_contracts(project_dir: Path, specs_dir: str = "specs") -> list[Contract]:
    """
    Load and validate contracts from contracts.yaml.

    Args:
        project_dir: Project directory path
        specs_dir: Name of specs directory (default: "specs")

    Returns:
        List of Contract objects

    Raises:
        ArchitectureValidationError: If YAML is malformed or required fields missing
    """
    contracts_path = find_contracts_path(project_dir, specs_dir)
    if contracts_path is None:
        return []
    contracts_list = _validate_yaml_list(
        contracts_path, "contracts.yaml", "contracts", "contract"
    )

    contracts = []
    for i, c in enumerate(contracts_list):
        # Check required field: name
        if "name" not in c:
            raise ArchitectureValidationError(
                "contracts.yaml", f"Contract at index {i} missing required field: name"
            )

        # endpoints is required (can be empty list)
        endpoints_data = c.get("endpoints", [])
        if not isinstance(endpoints_data, list):
            raise ArchitectureValidationError(
                "contracts.yaml",
                f"Contract '{c['name']}' has invalid 'endpoints': expected list",
            )

        endpoints = []
        for j, ep in enumerate(endpoints_data):
            if not isinstance(ep, dict):
                raise ArchitectureValidationError(
                    "contracts.yaml",
                    f"Contract '{c['name']}' endpoint at index {j}: expected dict",
                )

            # path and method are required for endpoints
            if "path" not in ep:
                raise ArchitectureValidationError(
                    "contracts.yaml",
                    f"Contract '{c['name']}' endpoint at index {j} missing: path",
                )
            if "method" not in ep:
                raise ArchitectureValidationError(
                    "contracts.yaml",
                    f"Contract '{c['name']}' endpoint at index {j} missing: method",
                )

            endpoints.append(
                ContractEndpoint(
                    path=ep["path"],
                    method=ep["method"],
                )
            )

        contracts.append(
            Contract(
                name=c["name"],
                description=c.get("description", ""),
                endpoints=endpoints,
            )
        )

    return contracts


def load_schemas(project_dir: Path, specs_dir: str = "specs") -> list[Schema]:
    """
    Load and validate schemas from schemas.yaml.

    Args:
        project_dir: Project directory path
        specs_dir: Name of specs directory (default: "specs")

    Returns:
        List of Schema objects

    Raises:
        ArchitectureValidationError: If YAML is malformed or required fields missing
    """
    schemas_path = find_schemas_path(project_dir, specs_dir)
    if schemas_path is None:
        return []
    schemas_list = _validate_yaml_list(
        schemas_path, "schemas.yaml", "schemas", "schema"
    )

    schemas = []
    for i, s in enumerate(schemas_list):
        # Check required field: name
        if "name" not in s:
            raise ArchitectureValidationError(
                "schemas.yaml", f"Schema at index {i} missing required field: name"
            )

        # fields is required (can be empty list)
        fields_data = s.get("fields", [])
        if not isinstance(fields_data, list):
            raise ArchitectureValidationError(
                "schemas.yaml",
                f"Schema '{s['name']}' has invalid 'fields': expected list",
            )

        fields = []
        for j, f in enumerate(fields_data):
            if not isinstance(f, dict):
                raise ArchitectureValidationError(
                    "schemas.yaml",
                    f"Schema '{s['name']}' field at index {j}: expected dict",
                )

            # name and type are required for fields
            if "name" not in f:
                raise ArchitectureValidationError(
                    "schemas.yaml",
                    f"Schema '{s['name']}' field at index {j} missing: name",
                )
            if "type" not in f:
                raise ArchitectureValidationError(
                    "schemas.yaml",
                    f"Schema '{s['name']}' field at index {j} missing: type",
                )

            fields.append(
                SchemaField(
                    name=f["name"],
                    type=f["type"],
                    constraints=f.get("constraints", []),
                )
            )

        schemas.append(
            Schema(
                name=s["name"],
                description=s.get("description", ""),
                fields=fields,
            )
        )

    return schemas


def validate_architecture_files(
    project_dir: Path, specs_dir: str = "specs"
) -> tuple[bool, list[str]]:
    """
    Validate all architecture files exist and contain valid YAML with required fields.

    This is a comprehensive validation that checks:
    1. All three required files exist (contracts.yaml, schemas.yaml, decisions.yaml)
    2. Each file contains valid YAML
    3. Each file has the required structure and fields

    Args:
        project_dir: Project directory path
        specs_dir: Name of specs directory (default: "specs")

    Returns:
        (success, errors) tuple where:
        - success: True if all validations pass
        - errors: List of error messages (empty if success)
    """
    errors = []
    arch_dir = find_architecture_dir(project_dir, specs_dir)

    # Check directory exists
    if arch_dir is None:
        return False, ["Architecture directory does not exist"]

    # Check all required files exist
    for filename in REQUIRED_FILES:
        if not (arch_dir / filename).exists():
            errors.append(f"Missing required file: {filename}")

    if errors:
        return False, errors

    # Validate contracts.yaml
    try:
        load_contracts(project_dir, specs_dir)
    except ArchitectureValidationError as e:
        errors.append(str(e))

    # Validate schemas.yaml
    try:
        load_schemas(project_dir, specs_dir)
    except ArchitectureValidationError as e:
        errors.append(str(e))

    # Validate decisions.yaml
    try:
        load_decisions(project_dir, specs_dir)
    except DecisionLoadError as e:
        errors.append(f"decisions.yaml: {e}")

    return len(errors) == 0, errors


def cleanup_partial_architecture(project_dir: Path, specs_dir: str = "specs") -> bool:
    """
    Clean up partial architecture directory if present.

    If the architecture phase fails partway through, this removes the incomplete
    architecture/ directory to avoid confusing the coding agent. Checks both
    canonical ({specs_dir}/architecture/) and legacy (architecture/) locations.

    Args:
        project_dir: Project directory path
        specs_dir: Name of specs directory (default: "specs")

    Returns:
        True if cleanup was performed, False if no cleanup needed
    """

    def _cleanup_dir(arch_dir: Path) -> bool:
        """Helper to clean up a specific architecture directory."""
        if not arch_dir.exists():
            return False

        # Safety check: verify it's actually a directory (not a symlink to a directory)
        if not arch_dir.is_dir() or arch_dir.is_symlink():
            return False

        # Safety check: verify arch_dir is actually within project_dir
        # This prevents path traversal attacks via symlinks or malicious paths
        try:
            resolved_arch = arch_dir.resolve()
            resolved_project = project_dir.resolve()
            if not resolved_arch.is_relative_to(resolved_project):
                return False
        except (ValueError, OSError):
            # resolve() can raise OSError on broken symlinks, ValueError on relative paths
            return False

        # Check if all required files exist
        all_exist = all((arch_dir / f).exists() for f in REQUIRED_FILES)

        if all_exist:
            # Architecture is complete - don't clean up
            return False

        # Partial architecture exists - clean it up
        shutil.rmtree(arch_dir)
        return True

    # Check canonical location first ({specs_dir}/architecture/)
    canonical_dir = project_dir / specs_dir / ARCH_DIR_NAME
    if _cleanup_dir(canonical_dir):
        return True

    # Check legacy location (architecture/ in project root)
    legacy_dir = project_dir / ARCH_DIR_NAME
    return _cleanup_dir(legacy_dir)
