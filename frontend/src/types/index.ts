// ── Enums ─────────────────────────────────────────────────────────────────
export type UserRole = "viewer" | "analyst" | "admin";
export type TransactionType = "income" | "expense";

// ── Auth ──────────────────────────────────────────────────────────────────
export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// ── User ──────────────────────────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface UserCreate {
  email: string;
  name: string;
  password: string;
  role: UserRole;
}

export interface UserUpdate {
  name?: string;
  role?: UserRole;
  is_active?: boolean;
}

// ── Transaction ───────────────────────────────────────────────────────────
export interface Transaction {
  id: string;
  amount: number;
  type: TransactionType;
  category: string;
  date: string;
  description?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface TransactionCreate {
  amount: number;
  type: TransactionType;
  category: string;
  date: string;
  description?: string;
}

export interface TransactionUpdate {
  amount?: number;
  type?: TransactionType;
  category?: string;
  date?: string;
  description?: string;
}

export interface PaginatedTransactions {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Dashboard ─────────────────────────────────────────────────────────────
export interface CategoryTotal {
  category: string;
  total: number;
  count: number;
}

export interface MonthlyTrend {
  year: number;
  month: number;
  income: number;
  expense: number;
  net: number;
}

export interface DashboardSummary {
  total_income: number;
  total_expense: number;
  net_balance: number;
  transaction_count: number;
  income_by_category: CategoryTotal[];
  expense_by_category: CategoryTotal[];
  monthly_trends: MonthlyTrend[];
  recent_transactions: Transaction[];
}
