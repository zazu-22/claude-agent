"""
Architecture File Validation
=============================

Validation functions for architecture lock files (contracts.yaml, schemas.yaml, decisions.yaml).
Ensures files contain valid YAML with required fields before coding sessions proceed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from claude_agent.decisions import load_decisions, DecisionLoadError

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


def get_architecture_dir(project_dir: Path) -> Path:
    """Get path to architecture directory."""
    return project_dir / ARCH_DIR_NAME


def get_contracts_path(project_dir: Path) -> Path:
    """Get path to contracts file."""
    return get_architecture_dir(project_dir) / CONTRACTS_FILE


def get_schemas_path(project_dir: Path) -> Path:
    """Get path to schemas file."""
    return get_architecture_dir(project_dir) / SCHEMAS_FILE


def load_contracts(project_dir: Path) -> list[Contract]:
    """
    Load and validate contracts from contracts.yaml.

    Args:
        project_dir: Project directory path

    Returns:
        List of Contract objects

    Raises:
        ArchitectureValidationError: If YAML is malformed or required fields missing
    """
    contracts_path = get_contracts_path(project_dir)

    if not contracts_path.exists():
        return []

    try:
        with open(contracts_path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ArchitectureValidationError(
            "contracts.yaml",
            f"Failed to parse YAML: {e}"
        ) from e

    if not isinstance(data, dict):
        raise ArchitectureValidationError(
            "contracts.yaml",
            f"Invalid format: expected dict, got {type(data).__name__}"
        )

    contracts_list = data.get("contracts", [])
    if not isinstance(contracts_list, list):
        raise ArchitectureValidationError(
            "contracts.yaml",
            f"Invalid 'contracts' field: expected list, got {type(contracts_list).__name__}"
        )

    contracts = []
    for i, c in enumerate(contracts_list):
        if not isinstance(c, dict):
            raise ArchitectureValidationError(
                "contracts.yaml",
                f"Invalid contract at index {i}: expected dict, got {type(c).__name__}"
            )

        # Check required field: name
        if "name" not in c:
            raise ArchitectureValidationError(
                "contracts.yaml",
                f"Contract at index {i} missing required field: name"
            )

        # endpoints is required (can be empty list)
        endpoints_data = c.get("endpoints", [])
        if not isinstance(endpoints_data, list):
            raise ArchitectureValidationError(
                "contracts.yaml",
                f"Contract '{c['name']}' has invalid 'endpoints': expected list"
            )

        endpoints = []
        for j, ep in enumerate(endpoints_data):
            if not isinstance(ep, dict):
                raise ArchitectureValidationError(
                    "contracts.yaml",
                    f"Contract '{c['name']}' endpoint at index {j}: expected dict"
                )

            # path and method are required for endpoints
            if "path" not in ep:
                raise ArchitectureValidationError(
                    "contracts.yaml",
                    f"Contract '{c['name']}' endpoint at index {j} missing: path"
                )
            if "method" not in ep:
                raise ArchitectureValidationError(
                    "contracts.yaml",
                    f"Contract '{c['name']}' endpoint at index {j} missing: method"
                )

            endpoints.append(ContractEndpoint(
                path=ep["path"],
                method=ep["method"],
            ))

        contracts.append(Contract(
            name=c["name"],
            description=c.get("description", ""),
            endpoints=endpoints,
        ))

    return contracts


def load_schemas(project_dir: Path) -> list[Schema]:
    """
    Load and validate schemas from schemas.yaml.

    Args:
        project_dir: Project directory path

    Returns:
        List of Schema objects

    Raises:
        ArchitectureValidationError: If YAML is malformed or required fields missing
    """
    schemas_path = get_schemas_path(project_dir)

    if not schemas_path.exists():
        return []

    try:
        with open(schemas_path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ArchitectureValidationError(
            "schemas.yaml",
            f"Failed to parse YAML: {e}"
        ) from e

    if not isinstance(data, dict):
        raise ArchitectureValidationError(
            "schemas.yaml",
            f"Invalid format: expected dict, got {type(data).__name__}"
        )

    schemas_list = data.get("schemas", [])
    if not isinstance(schemas_list, list):
        raise ArchitectureValidationError(
            "schemas.yaml",
            f"Invalid 'schemas' field: expected list, got {type(schemas_list).__name__}"
        )

    schemas = []
    for i, s in enumerate(schemas_list):
        if not isinstance(s, dict):
            raise ArchitectureValidationError(
                "schemas.yaml",
                f"Invalid schema at index {i}: expected dict, got {type(s).__name__}"
            )

        # Check required field: name
        if "name" not in s:
            raise ArchitectureValidationError(
                "schemas.yaml",
                f"Schema at index {i} missing required field: name"
            )

        # fields is required (can be empty list)
        fields_data = s.get("fields", [])
        if not isinstance(fields_data, list):
            raise ArchitectureValidationError(
                "schemas.yaml",
                f"Schema '{s['name']}' has invalid 'fields': expected list"
            )

        fields = []
        for j, f in enumerate(fields_data):
            if not isinstance(f, dict):
                raise ArchitectureValidationError(
                    "schemas.yaml",
                    f"Schema '{s['name']}' field at index {j}: expected dict"
                )

            # name and type are required for fields
            if "name" not in f:
                raise ArchitectureValidationError(
                    "schemas.yaml",
                    f"Schema '{s['name']}' field at index {j} missing: name"
                )
            if "type" not in f:
                raise ArchitectureValidationError(
                    "schemas.yaml",
                    f"Schema '{s['name']}' field at index {j} missing: type"
                )

            fields.append(SchemaField(
                name=f["name"],
                type=f["type"],
                constraints=f.get("constraints", []),
            ))

        schemas.append(Schema(
            name=s["name"],
            description=s.get("description", ""),
            fields=fields,
        ))

    return schemas


def validate_architecture_files(project_dir: Path) -> tuple[bool, list[str]]:
    """
    Validate all architecture files exist and contain valid YAML with required fields.

    This is a comprehensive validation that checks:
    1. All three required files exist (contracts.yaml, schemas.yaml, decisions.yaml)
    2. Each file contains valid YAML
    3. Each file has the required structure and fields

    Args:
        project_dir: Project directory path

    Returns:
        (success, errors) tuple where:
        - success: True if all validations pass
        - errors: List of error messages (empty if success)
    """
    errors = []
    arch_dir = get_architecture_dir(project_dir)

    # Check directory exists
    if not arch_dir.exists():
        return False, ["Architecture directory does not exist"]

    # Check all required files exist
    for filename in REQUIRED_FILES:
        if not (arch_dir / filename).exists():
            errors.append(f"Missing required file: {filename}")

    if errors:
        return False, errors

    # Validate contracts.yaml
    try:
        load_contracts(project_dir)
    except ArchitectureValidationError as e:
        errors.append(str(e))

    # Validate schemas.yaml
    try:
        load_schemas(project_dir)
    except ArchitectureValidationError as e:
        errors.append(str(e))

    # Validate decisions.yaml
    try:
        load_decisions(project_dir)
    except DecisionLoadError as e:
        errors.append(f"decisions.yaml: {e}")

    return len(errors) == 0, errors


def cleanup_partial_architecture(project_dir: Path) -> bool:
    """
    Clean up partial architecture directory if present.

    If the architecture phase fails partway through, this removes the incomplete
    architecture/ directory to avoid confusing the coding agent.

    Args:
        project_dir: Project directory path

    Returns:
        True if cleanup was performed, False if no cleanup needed
    """
    import shutil

    arch_dir = get_architecture_dir(project_dir)

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
