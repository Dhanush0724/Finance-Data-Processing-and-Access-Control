"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import { PaginatedTransactions, Transaction, TransactionCreate, TransactionType, User } from "@/types";
import { Plus, Search, Pencil, Trash2, X } from "lucide-react";
import clsx from "clsx";

const CATEGORIES = ["salary","freelance","investment","rental","bonus","rent","groceries","utilities","transport","entertainment","healthcare","subscriptions","other"];
const fmt = (n: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

const EMPTY_FORM: TransactionCreate = { amount: 0, type: "expense", category: "groceries", date: new Date().toISOString().slice(0,10), description: "" };

export default function TransactionsPage() {
  const user = getUser() as User;
  const canWrite = user?.role === "admin" || user?.role === "analyst";

  const [data, setData]         = useState<PaginatedTransactions | null>(null);
  const [page, setPage]         = useState(1);
  const [search, setSearch]     = useState("");
  const [typeFilter, setType]   = useState<TransactionType | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo]     = useState("");
  const [loading, setLoading]   = useState(true);
  const [showModal, setModal]   = useState(false);
  const [editing, setEditing]   = useState<Transaction | null>(null);
  const [form, setForm]         = useState<TransactionCreate>(EMPTY_FORM);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const params: any = { page, page_size: 15 };
    if (search)     params.search = search;
    if (typeFilter) params.type   = typeFilter;
    if (categoryFilter) params.category = categoryFilter;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    const { data: res } = await api.get<PaginatedTransactions>("/transactions", { params });
    setData(res);
    setLoading(false);
  }, [page, search, typeFilter, categoryFilter, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  function openCreate() { setEditing(null); setForm(EMPTY_FORM); setError(""); setModal(true); }
  function openEdit(tx: Transaction) {
    setEditing(tx);
    setForm({ amount: tx.amount, type: tx.type, category: tx.category, date: tx.date.slice(0,10), description: tx.description || "" });
    setError("");
    setModal(true);
  }

  async function handleSave() {
    if (form.amount <= 0) { setError("Amount must be greater than 0"); return; }
    setSaving(true); setError("");
    try {
      if (editing) {
        await api.patch(`/transactions/${editing.id}`, form);
      } else {
        await api.post("/transactions", { ...form, date: new Date(form.date).toISOString() });
      }
      setModal(false);
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  }

  async function handleDelete(tx: Transaction) {
    if (!confirm(`Delete this ${tx.type} of ${fmt(tx.amount)}?`)) return;
    await api.delete(`/transactions/${tx.id}`);
    load();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Transactions</h1>
          <p className="text-sm text-slate-500">{data?.total ?? "…"} records</p>
        </div>
        {canWrite && (
          <button onClick={openCreate}
            className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
            <Plus size={16} /> Add transaction
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="Search transactions…" />
        </div>
        <select value={typeFilter} onChange={(e) => { setType(e.target.value as any); setPage(1); }}
          className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500">
          <option value="">All types</option>
          <option value="income">Income</option>
          <option value="expense">Expense</option>
        </select>
        <select value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}
          className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500">
          <option value="">All categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
          className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
          placeholder="From date" />
        <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
          className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
          placeholder="To date" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr className="text-left text-xs text-slate-400">
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Category</th>
              <th className="px-4 py-3 font-medium">Description</th>
              <th className="px-4 py-3 font-medium text-right">Amount</th>
              {canWrite && <th className="px-4 py-3 font-medium w-20" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {loading ? (
              <tr><td colSpan={6} className="text-center py-10 text-slate-400">Loading…</td></tr>
            ) : data?.items.length === 0 ? (
              <tr><td colSpan={6} className="text-center py-10 text-slate-400">No transactions found</td></tr>
            ) : data?.items.map((tx) => (
              <tr key={tx.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3 text-slate-500">{new Date(tx.date).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium",
                    tx.type === "income" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600")}>
                    {tx.type}
                  </span>
                </td>
                <td className="px-4 py-3 capitalize text-slate-700">{tx.category}</td>
                <td className="px-4 py-3 text-slate-400 max-w-xs truncate">{tx.description || "—"}</td>
                <td className={clsx("px-4 py-3 text-right font-medium",
                  tx.type === "income" ? "text-green-600" : "text-red-500")}>
                  {tx.type === "income" ? "+" : "-"}{fmt(tx.amount)}
                </td>
                {canWrite && (
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end">
                      <button onClick={() => openEdit(tx)} className="text-slate-400 hover:text-blue-600 transition-colors"><Pencil size={14} /></button>
                      <button onClick={() => handleDelete(tx)} className="text-slate-400 hover:text-red-500 transition-colors"><Trash2 size={14} /></button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50">
            <span className="text-xs text-slate-400">Page {page} of {data.total_pages}</span>
            <div className="flex gap-2">
              <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                className="text-xs px-3 py-1 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-white transition-colors">Prev</button>
              <button disabled={page === data.total_pages} onClick={() => setPage(p => p + 1)}
                className="text-xs px-3 py-1 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-white transition-colors">Next</button>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 mx-4">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-slate-900">{editing ? "Edit transaction" : "Add transaction"}</h2>
              <button onClick={() => setModal(false)} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
                  <select value={form.type} onChange={(e) => setForm(f => ({ ...f, type: e.target.value as TransactionType }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500">
                    <option value="income">Income</option>
                    <option value="expense">Expense</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Amount (₹)</label>
                  <input type="number" min="0.01" step="0.01" value={form.amount || ""}
                    onChange={(e) => setForm(f => ({ ...f, amount: parseFloat(e.target.value) || 0 }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Category</label>
                  <select value={form.category} onChange={(e) => setForm(f => ({ ...f, category: e.target.value }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500">
                    {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Date</label>
                  <input type="date" value={form.date}
                    onChange={(e) => setForm(f => ({ ...f, date: e.target.value }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Description (optional)</label>
                <input type="text" value={form.description} maxLength={500}
                  onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="Notes about this entry" />
              </div>

              {error && <p className="text-xs text-red-500 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

              <div className="flex gap-3 pt-1">
                <button onClick={() => setModal(false)}
                  className="flex-1 text-sm border border-slate-200 text-slate-600 hover:bg-slate-50 py-2 rounded-lg transition-colors">
                  Cancel
                </button>
                <button onClick={handleSave} disabled={saving}
                  className="flex-1 text-sm bg-green-600 hover:bg-green-700 disabled:opacity-60 text-white font-medium py-2 rounded-lg transition-colors">
                  {saving ? "Saving…" : editing ? "Update" : "Create"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
