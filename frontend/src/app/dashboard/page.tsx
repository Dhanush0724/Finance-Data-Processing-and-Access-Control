"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DashboardSummary, Transaction } from "@/types";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { TrendingUp, TrendingDown, Wallet, Receipt } from "lucide-react";

const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const PIE_COLORS  = ["#22c55e","#3b82f6","#f59e0b","#ef4444","#8b5cf6","#06b6d4","#ec4899"];

function fmt(n: number) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
}

function StatCard({ label, value, sub, icon: Icon, color }: any) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
        </div>
        <div className={`p-2 rounded-xl ${color}`}><Icon size={20} /></div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData]       = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<DashboardSummary>("/dashboard/summary")
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-slate-400 text-sm">Loading…</div>;
  if (!data)   return <div className="text-red-500 text-sm">Failed to load summary.</div>;

  const chartData = data.monthly_trends.map((m) => ({
    name: MONTH_NAMES[m.month - 1],
    income: m.income,
    expense: m.expense,
    net: m.net,
  }));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Overview</h1>
        <p className="text-sm text-slate-500">All-time financial summary</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard label="Total Income"   value={fmt(data.total_income)}   icon={TrendingUp}   color="bg-green-50 text-green-600" />
        <StatCard label="Total Expenses" value={fmt(data.total_expense)}  icon={TrendingDown} color="bg-red-50 text-red-500" />
        <StatCard label="Net Balance"    value={fmt(data.net_balance)}    icon={Wallet}       color="bg-blue-50 text-blue-600" />
        <StatCard label="Transactions"   value={data.transaction_count}   icon={Receipt}      color="bg-slate-100 text-slate-600" sub="total records" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Monthly trend area chart */}
        <div className="xl:col-span-2 bg-white rounded-2xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-4">Monthly Trends</p>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="gi" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.15}/>
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="ge" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.15}/>
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} tickLine={false} axisLine={false}/>
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`}/>
              <Tooltip formatter={(v: number) => fmt(v)} />
              <Legend />
              <Area type="monotone" dataKey="income"  stroke="#22c55e" fill="url(#gi)" strokeWidth={2} name="Income" />
              <Area type="monotone" dataKey="expense" stroke="#ef4444" fill="url(#ge)" strokeWidth={2} name="Expense" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Expense by category pie */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-4">Expenses by Category</p>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={data.expense_by_category} dataKey="total" nameKey="category"
                   cx="50%" cy="50%" outerRadius={75} label={false}>
                {data.expense_by_category.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => fmt(v)} />
              <Legend formatter={(v) => v} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent transactions */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <p className="text-sm font-semibold text-slate-700 mb-4">Recent Activity</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
              <th className="pb-2 font-medium">Date</th>
              <th className="pb-2 font-medium">Category</th>
              <th className="pb-2 font-medium">Description</th>
              <th className="pb-2 font-medium text-right">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {data.recent_transactions.map((tx) => (
              <tr key={tx.id} className="py-2">
                <td className="py-2 text-slate-500">{new Date(tx.date).toLocaleDateString()}</td>
                <td className="py-2 capitalize">{tx.category}</td>
                <td className="py-2 text-slate-400 truncate max-w-xs">{tx.description || "—"}</td>
                <td className={`py-2 text-right font-medium ${tx.type === "income" ? "text-green-600" : "text-red-500"}`}>
                  {tx.type === "income" ? "+" : "-"}{fmt(tx.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
