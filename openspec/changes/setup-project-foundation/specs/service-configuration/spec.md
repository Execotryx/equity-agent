# Spec Delta

## Purpose

Defines how the research service loads, validates and protects its runtime configuration and secrets, and how it
reports its configuration state to developers and the frontend.

## ADDED Requirements

### Requirement: Required settings are validated at startup
The service SHALL refuse to start when a required setting is missing or empty. The required settings are the
Anthropic API key, the web-search API key and the SEC EDGAR identity. The error message SHALL name each missing
setting.

#### Scenario: Missing SEC identity
- **WHEN** the service starts without an SEC EDGAR identity configured
- **THEN** startup fails with an error that names the missing EDGAR identity setting

#### Scenario: All required settings present
- **WHEN** the service starts with all required settings configured
- **THEN** startup succeeds and the health endpoint responds

### Requirement: Secrets are never exposed
The service MUST NOT include API key values in logs, error messages, HTTP responses or the string form of its
settings object.

#### Scenario: Settings are printed
- **WHEN** the settings object is converted to a string or logged
- **THEN** the output contains no API key value

#### Scenario: Upstream authentication fails
- **WHEN** an external API rejects a key and the error is reported
- **THEN** the reported message does not contain the key value

### Requirement: Per-agent model and effort are configurable
The service SHALL let each LLM agent (Comps, Risk, Analyst, Writer) use its own model identifier and effort level
from configuration. Defaults SHALL be model `claude-opus-5-5` with effort `low` for Comps, Risk and Analyst, and
model `claude-sonnet-5-5` with effort `low` for the Writer.

#### Scenario: Defaults applied
- **WHEN** no per-agent model or effort settings are provided
- **THEN** Comps, Risk and Analyst resolve to `claude-opus-5-5` with effort `low`, and the Writer resolves to `claude-sonnet-5-5` with effort `low`

#### Scenario: Override one agent
- **WHEN** only the Writer model is set to `claude-haiku-4-5`
- **THEN** the Writer uses `claude-haiku-4-5` and the other agents keep their defaults

#### Scenario: Invalid effort value
- **WHEN** an effort setting has a value other than low, medium, high, xhigh or max
- **THEN** startup fails with an error naming the invalid setting

### Requirement: Health endpoint reports configuration safely
The service SHALL expose a health endpoint. It SHALL return the service status, the configured model and effort per
agent, and a true/false presence flag for each external credential. It SHALL never return credential values.

#### Scenario: Health check
- **WHEN** a client requests the health endpoint
- **THEN** the response has HTTP 200 and contains the status, the per-agent models and efforts, and boolean credential flags without any key values

### Requirement: Single command starts the application locally
The project SHALL provide one command that starts the backend API and the frontend dev server together on the
local machine, without containers or remote hosting.

#### Scenario: Start both processes
- **WHEN** the developer runs the documented start command from the repository root
- **THEN** the backend listens on port 8000 and the frontend on port 3000

### Requirement: Demo start command without development overhead
The project SHALL provide a second start command for demos. It SHALL build the frontend ahead of time and serve
the built pages. It SHALL run the backend without restarting on source-file changes.

#### Scenario: Source file saved during a demo
- **WHEN** the application was started with the demo start command and a backend source file is saved
- **THEN** the backend process does not restart

#### Scenario: First page load
- **WHEN** the home page is opened for the first time after the demo start command reports ready
- **THEN** it is served from the pre-built frontend without compiling the page on request
