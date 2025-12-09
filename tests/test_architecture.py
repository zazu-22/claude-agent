"""
Test architecture file validation functionality.

Tests verify:
- Contracts load and validate correctly
- Schemas load and validate correctly
- Comprehensive validation catches all issues
- Partial architecture cleanup works correctly
"""

import pytest
from pathlib import Path

from claude_agent.architecture import (
    ArchitectureValidationError,
    Contract,
    ContractEndpoint,
    Schema,
    SchemaField,
    load_contracts,
    load_schemas,
    validate_architecture_files,
    cleanup_partial_architecture,
)


class TestLoadContracts:
    """Test loading contracts from file."""

    def test_load_nonexistent(self, tmp_path):
        """Returns empty list when file doesn't exist."""
        contracts = load_contracts(tmp_path)
        assert contracts == []

    def test_load_empty_contracts(self, tmp_path):
        """Returns empty list when contracts list is empty."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: []")

        contracts = load_contracts(tmp_path)
        assert contracts == []

    def test_load_valid_contract(self, tmp_path):
        """Loads valid contract correctly."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - name: user_auth
    description: User authentication endpoints
    endpoints:
      - path: /api/auth/login
        method: POST
      - path: /api/auth/logout
        method: POST
""")

        contracts = load_contracts(tmp_path)
        assert len(contracts) == 1
        assert contracts[0].name == "user_auth"
        assert contracts[0].description == "User authentication endpoints"
        assert len(contracts[0].endpoints) == 2
        assert contracts[0].endpoints[0].path == "/api/auth/login"
        assert contracts[0].endpoints[0].method == "POST"

    def test_load_contract_minimal_fields(self, tmp_path):
        """Loads contract with only required fields."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - name: minimal
    endpoints: []
""")

        contracts = load_contracts(tmp_path)
        assert len(contracts) == 1
        assert contracts[0].name == "minimal"
        assert contracts[0].description == ""
        assert contracts[0].endpoints == []


class TestLoadContractsErrorHandling:
    """Test error handling for malformed contracts files."""

    def test_malformed_yaml(self, tmp_path):
        """Raises error for invalid YAML syntax."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: [unclosed")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "contracts.yaml" in str(exc_info.value)
        assert "Failed to parse YAML" in str(exc_info.value)

    def test_non_dict_root(self, tmp_path):
        """Raises error when root is not a dict."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("- just a list")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "expected dict, got list" in str(exc_info.value)

    def test_contracts_not_list(self, tmp_path):
        """Raises error when contracts field is not a list."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: not_a_list")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "expected list, got str" in str(exc_info.value)

    def test_contract_not_dict(self, tmp_path):
        """Raises error when a contract entry is not a dict."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - "just a string"
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "Invalid contract at index 0" in str(exc_info.value)

    def test_missing_name(self, tmp_path):
        """Raises error when contract is missing name."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - endpoints: []
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "missing required field: name" in str(exc_info.value)

    def test_endpoints_not_list(self, tmp_path):
        """Raises error when endpoints is not a list."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - name: test
    endpoints: not_a_list
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "invalid 'endpoints': expected list" in str(exc_info.value)

    def test_endpoint_missing_path(self, tmp_path):
        """Raises error when endpoint is missing path."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - name: test
    endpoints:
      - method: POST
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "endpoint at index 0 missing: path" in str(exc_info.value)

    def test_endpoint_missing_method(self, tmp_path):
        """Raises error when endpoint is missing method."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - name: test
    endpoints:
      - path: /api/test
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_contracts(tmp_path)
        assert "endpoint at index 0 missing: method" in str(exc_info.value)


class TestLoadSchemas:
    """Test loading schemas from file."""

    def test_load_nonexistent(self, tmp_path):
        """Returns empty list when file doesn't exist."""
        schemas = load_schemas(tmp_path)
        assert schemas == []

    def test_load_empty_schemas(self, tmp_path):
        """Returns empty list when schemas list is empty."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: []")

        schemas = load_schemas(tmp_path)
        assert schemas == []

    def test_load_valid_schema(self, tmp_path):
        """Loads valid schema correctly."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("""
version: 1
schemas:
  - name: User
    description: User account entity
    fields:
      - name: id
        type: string
        constraints:
          - uuid
          - primary_key
      - name: email
        type: string
        constraints:
          - unique
""")

        schemas = load_schemas(tmp_path)
        assert len(schemas) == 1
        assert schemas[0].name == "User"
        assert schemas[0].description == "User account entity"
        assert len(schemas[0].fields) == 2
        assert schemas[0].fields[0].name == "id"
        assert schemas[0].fields[0].type == "string"
        assert schemas[0].fields[0].constraints == ["uuid", "primary_key"]

    def test_load_schema_minimal_fields(self, tmp_path):
        """Loads schema with only required fields."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("""
version: 1
schemas:
  - name: minimal
    fields: []
""")

        schemas = load_schemas(tmp_path)
        assert len(schemas) == 1
        assert schemas[0].name == "minimal"
        assert schemas[0].description == ""
        assert schemas[0].fields == []


class TestLoadSchemasErrorHandling:
    """Test error handling for malformed schemas files."""

    def test_malformed_yaml(self, tmp_path):
        """Raises error for invalid YAML syntax."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: [unclosed")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_schemas(tmp_path)
        assert "schemas.yaml" in str(exc_info.value)
        assert "Failed to parse YAML" in str(exc_info.value)

    def test_non_dict_root(self, tmp_path):
        """Raises error when root is not a dict."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("- just a list")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_schemas(tmp_path)
        assert "expected dict, got list" in str(exc_info.value)

    def test_schemas_not_list(self, tmp_path):
        """Raises error when schemas field is not a list."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: not_a_list")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_schemas(tmp_path)
        assert "expected list, got str" in str(exc_info.value)

    def test_missing_name(self, tmp_path):
        """Raises error when schema is missing name."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("""
version: 1
schemas:
  - fields: []
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_schemas(tmp_path)
        assert "missing required field: name" in str(exc_info.value)

    def test_field_missing_name(self, tmp_path):
        """Raises error when field is missing name."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("""
version: 1
schemas:
  - name: Test
    fields:
      - type: string
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_schemas(tmp_path)
        assert "field at index 0 missing: name" in str(exc_info.value)

    def test_field_missing_type(self, tmp_path):
        """Raises error when field is missing type."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "schemas.yaml").write_text("""
version: 1
schemas:
  - name: Test
    fields:
      - name: id
""")

        with pytest.raises(ArchitectureValidationError) as exc_info:
            load_schemas(tmp_path)
        assert "field at index 0 missing: type" in str(exc_info.value)


class TestValidateArchitectureFiles:
    """Test comprehensive architecture validation."""

    def test_all_valid(self, tmp_path):
        """Returns success when all files are valid."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("""
version: 1
contracts:
  - name: test
    endpoints: []
""")
        (arch_dir / "schemas.yaml").write_text("""
version: 1
schemas:
  - name: Test
    fields: []
""")
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
    choice: A
""")

        success, errors = validate_architecture_files(tmp_path)
        assert success is True
        assert errors == []

    def test_no_architecture_dir(self, tmp_path):
        """Returns failure when architecture directory doesn't exist."""
        success, errors = validate_architecture_files(tmp_path)
        assert success is False
        assert "Architecture directory does not exist" in errors

    def test_missing_file(self, tmp_path):
        """Returns failure when a required file is missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: []")
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: []")
        # Missing decisions.yaml

        success, errors = validate_architecture_files(tmp_path)
        assert success is False
        assert any("decisions.yaml" in e for e in errors)

    def test_invalid_contracts(self, tmp_path):
        """Returns failure when contracts.yaml is invalid."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: not_a_list")
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: []")
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
    choice: A
""")

        success, errors = validate_architecture_files(tmp_path)
        assert success is False
        assert any("contracts.yaml" in e for e in errors)

    def test_invalid_schemas(self, tmp_path):
        """Returns failure when schemas.yaml is invalid."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: []")
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: not_a_list")
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    topic: Test
    choice: A
""")

        success, errors = validate_architecture_files(tmp_path)
        assert success is False
        assert any("schemas.yaml" in e for e in errors)

    def test_invalid_decisions(self, tmp_path):
        """Returns failure when decisions.yaml is invalid."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: []")
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: []")
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
    # Missing topic and choice
""")

        success, errors = validate_architecture_files(tmp_path)
        assert success is False
        assert any("decisions.yaml" in e for e in errors)

    def test_multiple_errors(self, tmp_path):
        """Collects multiple errors when multiple files are invalid."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1\ncontracts: not_list")
        (arch_dir / "schemas.yaml").write_text("version: 1\nschemas: not_list")
        (arch_dir / "decisions.yaml").write_text("""
version: 1
decisions:
  - id: DR-001
""")

        success, errors = validate_architecture_files(tmp_path)
        assert success is False
        assert len(errors) >= 2  # At least contracts and schemas errors


class TestCleanupPartialArchitecture:
    """Test partial architecture cleanup."""

    def test_no_cleanup_when_no_dir(self, tmp_path):
        """Returns False when architecture directory doesn't exist."""
        result = cleanup_partial_architecture(tmp_path)
        assert result is False

    def test_no_cleanup_when_complete(self, tmp_path):
        """Returns False when architecture is complete."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "schemas.yaml").write_text("version: 1")
        (arch_dir / "decisions.yaml").write_text("version: 1")

        result = cleanup_partial_architecture(tmp_path)
        assert result is False
        assert arch_dir.exists()

    def test_cleanup_when_partial(self, tmp_path):
        """Removes directory when only some files exist."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        # Missing schemas.yaml and decisions.yaml

        result = cleanup_partial_architecture(tmp_path)
        assert result is True
        assert not arch_dir.exists()

    def test_cleanup_empty_directory(self, tmp_path):
        """Removes empty architecture directory."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()

        result = cleanup_partial_architecture(tmp_path)
        assert result is True
        assert not arch_dir.exists()

    def test_cleanup_with_extra_files(self, tmp_path):
        """Removes directory even with extra files when required files missing."""
        arch_dir = tmp_path / "architecture"
        arch_dir.mkdir()
        (arch_dir / "contracts.yaml").write_text("version: 1")
        (arch_dir / "extra.yaml").write_text("notes: extra file")
        # Missing schemas.yaml and decisions.yaml

        result = cleanup_partial_architecture(tmp_path)
        assert result is True
        assert not arch_dir.exists()
