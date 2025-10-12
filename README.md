# orchestron
The **Orchestron** project is a modular, extensible Python framework designed to manage and execute action nodes for task automation, with a focus on email processing and database integration. Located at `C:\workspace\orchestron` on your system, it uses a command-line interface (CLI) to run nodes like `emailsender`, `emailgetter`, and `dbwriter`, which handle sending emails, fetching emails, and storing data in a database, respectively. The project leverages Python’s `argparse`, `yaml`, `smtplib`, `imaplib`, and `sqlalchemy` libraries to provide a flexible system for orchestrating tasks, with a structure that supports dynamic node discovery and configuration. Below is a detailed description of the project based on the provided context and interactions.

### Project Overview
- **Name**: Orchestron (alternatively referred to as “NodeFlow” in earlier discussions, but “Orchestron” is used based on your workspace path `C:\workspace\orchestron`).
- **Purpose**: To create a framework for executing modular action nodes that perform specific tasks, such as sending emails, fetching emails, and writing data to a database, with the ability to chain tasks and configure them via a YAML file.
- **Core Components**:
  - **CLI Framework**: `node_framework.py` provides a CLI to list, run, or chain nodes.
  - **Action Nodes**: Python classes (`EmailSenderNode`, `EmailGetterNode`, `DBWriterNode`) in the `action_nodes` directory that inherit from a base `ActionNode` class.
  - **Configuration**: A `config.yaml` file for node settings (e.g., SMTP/IMAP credentials, database URL).
  - **Dependencies**: Managed via `uv` (a Python package manager) with `PyYAML` and `sqlalchemy` listed in `requirements.txt`.
- **Environment**: Runs in a Python virtual environment (`orchestron`), typically executed in PowerShell on Windows, with support for `uv run` for dependency resolution.
- **Key Features**:
  - Dynamic node discovery: Automatically loads nodes from `action_nodes`.
  - Parameter validation: Ensures nodes receive valid inputs.
  - Error handling and logging: Detailed logs for debugging.
  - Extensibility: Easy to add new nodes by creating Python files with `ActionNode` subclasses.
  - Gmail integration: Supports sending and fetching emails via SMTP/IMAP with app-specific passwords.
  - Database storage: Writes email data to a SQLite database (extendable to MySQL/PostgreSQL).

### Directory Structure
The project is organized as follows in `C:\workspace\orchestron`:

- **`node_framework.py`**: The main CLI script that manages node discovery, execution, and chaining. It supports three commands:
  - `list`: Displays available nodes and their parameters.
  - `run <node_name>`: Executes a specific node with provided arguments.
  - `chain <chain_name>`: Runs a sequence of nodes (e.g., `emailgetter_to_db` to fetch emails and store them in a database).
- **`action_nodes/`**:
  - `base_node.py`: Defines the `ActionNode` base class with abstract methods for parameter definition and validation.
  - `email_sender.py`: Implements `EmailSenderNode` to send emails via SMTP (e.g., `smtp.gmail.com`).
  - `email_getter.py`: Implements `EmailGetterNode` to fetch emails via IMAP (e.g., `imap.gmail.com`).
  - `db_writer.py`: Implements `DBWriterNode` to store email data in a SQLite database (`emails.db`).
- **`config.yaml`**: Configuration file with settings for each node (e.g., SMTP/IMAP credentials, database URL).
- **`emails.db`**: SQLite database (created by `db_writer`) storing email records with fields `id`, `from_email`, `subject`, `body`, `received_at`.
- **`requirements.txt`**:
  ```txt
  PyYAML>=6.0.0
  sqlalchemy>=2.0.0
  ```
- **`chain_email_to_db.py`** (optional): A script to chain `emailgetter` and `dbwriter` programmatically.

### Key Nodes and Functionality
1. **EmailSenderNode** (`email_sender.py`):
   - **Purpose**: Sends emails using SMTP.
   - **Parameters**: `to_email` (string, required), `subject` (string, required), `body` (string, required).
   - **Config**: `smtp_server`, `port`, `user`, `password` (uses Gmail app-specific password).
   - **Example Command**:
     ```powershell
     python node_framework.py --config config.yaml run emailsender --to_email recipient@example.com --subject "Test" --body "Hello"
     ```
   - **Output**: `{"status": "sent"}`

2. **EmailGetterNode** (`email_getter.py`):
   - **Purpose**: Fetches recent emails from an IMAP server (e.g., Gmail’s `imap.gmail.com`).
   - **Parameters**: `max_emails` (integer, optional, default 5).
   - **Config**: `imap_server`, `user`, `password` (uses Gmail app-specific password).
   - **Example Command**:
     ```powershell
     python node_framework.py --config config.yaml run emailgetter --max_emails 3
     ```
   - **Output**: A JSON list of email dictionaries (e.g., `[{"from": "sender@example.com", "subject": "Email 1", "body": "Content"}]`.

3. **DBWriterNode** (`db_writer.py`):
   - **Purpose**: Writes email data (from `emailgetter`) to a SQLite database.
   - **Parameters**: `emails` (list of dictionaries with `from`, `subject`, `body`, required).
   - **Config**: `db_url` (e.g., `sqlite:///emails.db`).
   - **Example Command** (standalone):
     ```powershell
     python action_nodes\db_writer.py --config config.yaml --emails "[{\"from\": \"test@example.com\", \"subject\": \"Test\", \"body\": \"Content\"}]"
     ```
   - **Output**: `{"status": "success", "count": 1}`

4. **Node Chaining**:
   - The `chain emailgetter_to_db` command fetches emails with `emailgetter` and writes them to the database with `dbwriter`.
   - **Command**:
     ```powershell
     python node_framework.py --config config.yaml chain emailgetter_to_db --max_emails 3
     ```
   - **Output**: `{"status": "success", "count": 3}`

### Configuration
- **`config.yaml`**:
  ```yaml
  emailsender:
    smtp_server: smtp.gmail.com
    port: 587
    user: your@email.com
    password: abcdefghijklmnop  # Gmail app-specific password
  emailgetter:
    imap_server: imap.gmail.com
    user: your@email.com
    password: qrstuvwxyz123456  # Gmail app-specific password
  dbwriter:
    db_url: sqlite:///emails.db
  ```
- **Environment Variables**: Can override `config.yaml` settings (e.g., `SMTP_PASSWORD`, `IMAP_PASSWORD`, `DB_URL`) for security.

### Workflow Example
1. **List Available Nodes**:
   ```powershell
   python node_framework.py --config config.yaml list
   ```
   Output:
   ```
   Available Nodes:
   Name: emailsender
   Description: Node to send an email. Config: {'smtp_server', 'port', 'user', 'password'}.
   Parameters:
     --to_email: Recipient email address (required)
     --subject: Email subject (required)
     --body: Email body (required)
   Name: emailgetter
   Description: Node to fetch recent emails. Config: {'imap_server', 'user', 'password'}.
   Parameters:
     --max_emails: Maximum emails to fetch (default: 5)
   Name: dbwriter
   Description: Node to write emails to a database. Config: {'db_url'}.
   Parameters:
     --emails: List of email dictionaries with 'from', 'subject', 'body' keys (required)
   ```

2. **Fetch and Store Emails**:
   ```powershell
   python node_framework.py --config config.yaml chain emailgetter_to_db --max_emails 3
   ```
   Fetches up to 3 emails and stores them in `emails.db`.

3. **Verify Database**:
   ```powershell
   python -c "import sqlite3; conn = sqlite3.connect('emails.db'); print(list(conn.execute('SELECT * FROM emails'))); conn.close()"
   ```

### Development and Debugging
- **Environment**: Uses `uv` for dependency management and script execution (e.g., `uv run python ...`). The virtual environment is named `orchestron`.
- **Debugging**: Supports VS Code debugging via `launch.json`:
  ```json
  {
      "version": "0.2.0",
      "configurations": [
          {
              "name": "Debug Orchestron Chain",
              "type": "python",
              "request": "launch",
              "program": "${workspaceFolder}/node_framework.py",
              "args": ["--config", "config.yaml", "chain", "emailgetter_to_db", "--max_emails", "3"],
              "console": "integratedTerminal",
              "python": "uv run python"
          }
      ]
  }
  ```
- **Debug Defaults**: Nodes like `emailsender` and `emailgetter` have debug-mode defaults to simplify testing.
- 🧩 Using Orchestron from Another Project

You can import Orchestron’s nodes as tools (for example, from another Python project or a LangChain/LangGraph workflow).

Step 1 — Import the public API
from orchestron.api import get_tool, list_tools

# List all tools
for t in list_tools():
    print(t["name"], ":", t["description"])

# Get a specific tool
email_tool = get_tool("emailgetter")

# Run the tool
emails = email_tool["function"](max_emails=3)
print(emails)

Step 2 — Integrate with LangChain (optional)
from langchain.tools import StructuredTool
from orchestron.api import list_tools

tools = [
    StructuredTool.from_function(
        func=t["function"],
        name=t["name"],
        description=t["description"]
    )
    for t in list_tools()
]

# Now each orchestron node can be used as a LangChain tool.


This enables other AI agents, workflow systems, or microservices to call Orchestron nodes dynamically without needing to invoke the CLI.
### Key Features and Benefits
- **Modularity**: New nodes can be added by creating Python files in `action_nodes` that inherit from `ActionNode`.
- **Extensibility**: The `chain` command allows task orchestration (e.g., `emailgetter` → `dbwriter`).
- **Robust Error Handling**: Detailed logging and parameter validation prevent common errors (e.g., missing config, invalid inputs).
- **Gmail Integration**: Supports secure email operations using app-specific passwords.
- **Database Support**: Stores email data in a structured database, with flexibility to switch to MySQL/PostgreSQL.
- **CLI Usability**: Simple commands (`list`, `run`, `chain`) with clear help text.

### Challenges Addressed
Throughout our interactions, we resolved:
- **Node Discovery**: Fixed issues with `emailsender` not found due to file naming (`email__sender.py` vs. `email_sender.py`).
- **Gmail Authentication**: Resolved `534-5.7.9 Application-specific password required` by using app-specific passwords.
- **Command Parsing**: Fixed PowerShell argument issues (e.g., `Unexpected token 'python'`) by correcting command syntax.
- **Database Integration**: Added `db_writer.py` and a `chain` command to store emails.

### Future Enhancements
- **More Chains**: Add support for additional node chains (e.g., `emailsender_to_db` to log sent emails).
- **Database Flexibility**: Support MySQL/PostgreSQL by updating `db_url` and installing drivers.
- **Advanced Email Parsing**: Enhance `email_getter.py` to handle HTML emails or attachments.
- **Security**: Move all credentials to environment variables or a secrets manager.
- **CLI Extensions**: Add options to filter emails (e.g., by sender, date) or customize database fields.

### Security Notes
- **Credentials**: Use app-specific passwords for Gmail and environment variables for production.
- **Database**: Ensure `emails.db` is backed up and access-controlled, especially if storing sensitive email data.

If you need specific details (e.g., adding new nodes, modifying `db_writer` fields, or changing the database), please share your requirements, and I can extend the project further!