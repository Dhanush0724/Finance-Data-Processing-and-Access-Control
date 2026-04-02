"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import { User, UserCreate, UserUpdate, UserRole } from "@/types";
import { Plus, Pencil, Trash2, X, ShieldCheck } from "lucide-react";
import clsx from "clsx";

const ROLE_BADGE: Record<UserRole, string> = {
  admin:   "bg-purple-100 text-purple-700",
  analyst: "bg-blue-100 text-blue-700",
  viewer:  "bg-slate-100 text-slate-600",
};

const EMPTY_FORM: UserCreate = { email: "", name: "", password: "", role: "viewer" };

export default function UsersPage() {
  const router = useRouter();
  const me = getUser();

  useEffect(() => {
    if (me?.role !== "admin") router.replace("/dashboard");
  }, [me, router]);

  const [users, setUsers]     = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setModal] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm]       = useState<UserCreate>(EMPTY_FORM);
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState("");

  async function load() {
    setLoading(true);
    const { data } = await api.get<User[]>("/users");
    setUsers(data);
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setError("");
    setModal(true);
  }

  function openEdit(u: User) {
    setEditing(u);
    setForm({ email: u.email, name: u.name, password: "", role: u.role });
    setError("");
    setModal(true);
  }

  async function handleSave() {
    if (!form.name.trim()) { setError("Name is required"); return; }
    if (!editing && !form.password) { setError("Password is required"); return; }
    setSaving(true);
    setError("");
    try {
      if (editing) {
        const patch: UserUpdate = { name: form.name, role: form.role };
        await api.patch(`/users/${editing.id}`, patch);
      } else {
        await api.post("/users", form);
      }
      setModal(false);
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleActive(u: User) {
    await api.patch(`/users/${u.id}`, { is_active: !u.is_active });
    load();
  }

  async function handleDelete(u: User) {
    if (!confirm(`Permanently delete ${u.name}?`)) return;
    await api.delete(`/users/${u.id}`);
    load();
  }

  if (me?.role !== "admin") return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Users</h1>
          <p className="text-sm text-slate-500">{users.length} accounts</p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus size={16} /> Add user
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr className="text-left text-xs text-slate-400">
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Joined</th>
              <th className="px-4 py-3 font-medium w-24" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {loading ? (
              <tr><td colSpan={6} className="text-center py-10 text-slate-400">Loading…</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3 font-medium text-slate-900 flex items-center gap-2">
                  {u.role === "admin" && <ShieldCheck size={14} className="text-purple-500 shrink-0" />}
                  {u.name}
                  {u.id === me?.id && <span className="text-xs text-slate-400">(you)</span>}
                </td>
                <td className="px-4 py-3 text-slate-500">{u.email}</td>
                <td className="px-4 py-3">
                  <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", ROLE_BADGE[u.role])}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => handleToggleActive(u)}
                    disabled={u.id === me?.id}
                    className={clsx(
                      "text-xs px-2 py-0.5 rounded-full font-medium transition-colors disabled:cursor-not-allowed",
                      u.is_active
                        ? "bg-green-50 text-green-700 hover:bg-green-100"
                        : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                    )}
                  >
                    {u.is_active ? "active" : "inactive"}
                  </button>
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 justify-end">
                    <button onClick={() => openEdit(u)} className="text-slate-400 hover:text-blue-600 transition-colors">
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(u)}
                      disabled={u.id === me?.id}
                      className="text-slate-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 mx-4">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-slate-900">
                {editing ? "Edit user" : "Add user"}
              </h2>
              <button onClick={() => setModal(false)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Full name</label>
                <input
                  type="text" value={form.name}
                  onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="Jane Smith"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Email</label>
                <input
                  type="email" value={form.email}
                  disabled={!!editing}
                  onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 disabled:bg-slate-50 disabled:text-slate-400"
                  placeholder="jane@example.com"
                />
              </div>

              {!editing && (
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Password</label>
                  <input
                    type="password" value={form.password} minLength={6}
                    onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                    placeholder="Min 6 characters"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Role</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm(f => ({ ...f, role: e.target.value as UserRole }))}
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                >
                  <option value="viewer">Viewer — read-only dashboard access</option>
                  <option value="analyst">Analyst — view + create/edit records</option>
                  <option value="admin">Admin — full access + user management</option>
                </select>
              </div>

              {error && (
                <p className="text-xs text-red-500 bg-red-50 px-3 py-2 rounded-lg">{error}</p>
              )}

              <div className="flex gap-3 pt-1">
                <button
                  onClick={() => setModal(false)}
                  className="flex-1 text-sm border border-slate-200 text-slate-600 hover:bg-slate-50 py-2 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave} disabled={saving}
                  className="flex-1 text-sm bg-green-600 hover:bg-green-700 disabled:opacity-60 text-white font-medium py-2 rounded-lg transition-colors"
                >
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
