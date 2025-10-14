# Payouto Bank Statement Analyser

A powerful and flexible tool for parsing, analyzing, and extracting insights from Nigerian bank statements in PDF format.

## Features

- **Multi-Bank Support**: Compatible with major Nigerian banks including:

  - Access Bank
  - First Bank
  - GTBank
  - UBA
  - Zenith Bank
  - Fidelity
  - FCMB
  - And many more...

- **Comprehensive Analysis**:
  - Transaction parsing and normalization
  - Statement metadata extraction
  - Data validation and integrity checks
  - Transaction categorization
  - Financial insights and summaries

## Getting Started

### Prerequisites

- Node.js (Latest LTS version)
- Python 3.x
- pip (Python package manager)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/KachiKaduru/payouto-bank-analyser.git

cd payouto-bank-analyser
```

1. Install Node.js dependencies:

```bash
npm install
```

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

1. Run the development server:

```bash
npm run dev
```

The application should now be running at [http://localhost:3000](http://localhost:3000)

## Tech Stack

- **Frontend**

  - Next.js
  - TypeScript
  - TailwindCSS
  - Framer Motion
  - Zustand (State Management)

- **Backend**
  - Python
  - pdfplumber (PDF Processing)
  - FastAPI (API Server)

## How It Works

1. **Upload:** Users upload their bank statement PDF and select their bank

2. **Processing:**

   - The system detects the bank and statement format
   - Applies the appropriate parsing strategy
   - Extracts transaction data and metadata
   - Performs validation checks

3. **Analysis:**

   - Transactions are normalized and categorized
   - Metadata is extracted and validated
   - Legitimacy checks are performed

4. **Results:**

   - View parsed transactions in an interactive table
   - Access statement metadata and validation results
   - Export data to Excel for further analysis

5. **Security**
   - PDF passwords are handled securely
   - All processing is done locally
   - No data is stored on servers
   - Secure validation checks for statement legitimacy

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- All the Nigerian banks for their statement formats
- The open-source community for various tools and libraries used in this project.
