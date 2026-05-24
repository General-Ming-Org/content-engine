import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { listUsers, setUserRole, setUserActive } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Admin() {
  const { user: me } = useAuth();
  const qc = useQueryClient();

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: "admin" | "user" }) =>
      setUserRole(id, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const activeMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      setUserActive(id, is_active),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  if (me?.role !== "admin") {
    return (
      <div className="p-8 text-neutral-400">
        This page is admin-only.
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold mb-1">Users</h1>
      <p className="text-sm text-neutral-400 mb-8">
        Manage accounts. The first account is auto-promoted to admin.
      </p>

      {isLoading && <div className="text-neutral-500">Loading…</div>}

      {users && (
        <div className="border border-neutral-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-neutral-900 text-neutral-400">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Email</th>
                <th className="text-left px-4 py-3 font-medium">Name</th>
                <th className="text-left px-4 py-3 font-medium">Role</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Last login</th>
                <th className="text-right px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-neutral-800">
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3 text-neutral-400">{u.name || "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        u.role === "admin"
                          ? "px-2 py-0.5 rounded text-xs bg-purple-950/50 text-purple-300 border border-purple-900/50"
                          : "px-2 py-0.5 rounded text-xs bg-neutral-800 text-neutral-400"
                      }
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="text-green-400">active</span>
                    ) : (
                      <span className="text-neutral-500">disabled</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-neutral-500 text-xs">
                    {(u as any).last_login_at
                      ? new Date((u as any).last_login_at).toLocaleString()
                      : "never"}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    {u.id !== me.id && (
                      <>
                        <button
                          onClick={() =>
                            roleMutation.mutate({
                              id: u.id,
                              role: u.role === "admin" ? "user" : "admin",
                            })
                          }
                          className="text-xs px-2 py-1 border border-neutral-700 rounded hover:bg-neutral-800"
                        >
                          {u.role === "admin" ? "Demote" : "Promote"}
                        </button>
                        <button
                          onClick={() =>
                            activeMutation.mutate({
                              id: u.id,
                              is_active: !u.is_active,
                            })
                          }
                          className="text-xs px-2 py-1 border border-neutral-700 rounded hover:bg-neutral-800"
                        >
                          {u.is_active ? "Disable" : "Enable"}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
