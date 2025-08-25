export const FIELD_MAPPINGS = {
  TXN_DATE: [
    "txn date",
    "trans date",
    "transaction date",
    "date",
    "post date",
    "posted date",
    "trans. date",
  ],
  VAL_DATE: ["val date", "value date", "effective date", "value. date", "valuedate", "date"],
  REFERENCE: ["reference", "ref", "transaction id", "txn id", "ref. number", "reference number"],
  REMARKS: ["remarks", "description", "narration", "comment", "transaction details", "details"],
  DEBIT: ["debit", "withdrawal", "dr", "withdrawal(DR)", "debits", "money out", "debit (NGN)"],
  CREDIT: [
    "credit",
    "deposit",
    "cr",
    "deposit(CR)",
    "credits",
    "money in",
    "credit(₦)",
    "credit (NGN)",
  ],
  BALANCE: ["balance", "bal", "account balance", " balance(₦)", "balance (NGN)"],
  AMOUNT: ["amount", "txn amount", "transaction amount", "balance(₦)"],
};

export const banksList = [
  { id: 1, value: "first-bank", label: "First Bank" },
  { id: 2, value: "zenith", label: "Zenith Bank" },
];
