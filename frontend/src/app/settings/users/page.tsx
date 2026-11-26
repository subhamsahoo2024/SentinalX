'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Pencil,
  Plus,
  Shield,
  Users,
  X,
  XCircle,
} from 'lucide-react';
import { useIsClient } from '@/hooks/use-is-client';
import {
  createTeam,
  createUser,
  fetchTeams,
  fetchUsers,
  updateUser,
} from '@/lib/api';
import { getAuthUserSnapshot, subscribeAuth } from '@/lib/auth';
import { formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ActorRole, TeamDTO, UserSummaryDTO } from '@/types/telemetry';

const ROLE_OPTIONS: ActorRole[] = ['viewer', 'operator', 'approver', 'admin'];

function roleBadgeClasses(role: string): string {
  switch (role) {
    case 'admin':
      return 'border-purple-300 bg-purple-50 text-purple-700 dark:border-purple-500/40 dark:bg-purple-500/15 dark:text-purple-300';
    case 'approver':
      return 'border-[#93C5FD] bg-[#EFF6FF] text-[#0257D5] dark:border-[#00C2FF]/40 dark:bg-[#0257D5]/25 dark:text-[#7DD3FC]';
    case 'operator':
      return 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-300';
    default:
      return 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
  }
}

interface TeamSelectorProps {
  teams: TeamDTO[];
  selected: string[];
  onChange: (next: string[]) => void;
}

function TeamScopeSelector({ teams, selected, onChange }: TeamSelectorProps) {
  const isAll = selected.includes('*');

  const toggleAll = () => {
    onChange(isAll ? [] : ['*']);
  };

  const toggleTeam = (teamId: string) => {
    const withoutAll = selected.filter((t) => t !== '*');
    if (withoutAll.includes(teamId)) {
      onChange(withoutAll.filter((t) => t !== teamId));
    } else {
      onChange([...withoutAll, teamId]);
    }
  };

  return (
    <div className="space-y-2">
      <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-200 cursor-pointer">
        <input
          type="checkbox"
          checked={isAll}
          onChange={toggleAll}
          className="h-4 w-4 rounded border-slate-300 text-[#0257D5] focus:ring-[#0257D5]"
        />
        <span>All Teams (`*`)</span>
      </label>

      {!isAll && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {teams.map((team) => {
            const active = selected.includes(team.team_id);
            return (
              <button
                key={team.team_id}
                type="button"
                onClick={() => toggleTeam(team.team_id)}
                className={cn(
                  'rounded-md border px-2.5 py-1 text-xs font-mono transition-colors',
                  active
                    ? 'border-[#0257D5] bg-[#EFF6FF] text-[#0257D5] dark:border-[#00C2FF] dark:bg-[#0257D5]/25 dark:text-[#7DD3FC]'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-[#1D3868] dark:bg-[#0A1B3B] dark:text-slate-300 dark:hover:bg-[#102650]',
                )}
              >
                {team.team_id}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function UsersAndTeamsPage() {
  const mounted = useIsClient();
  const currentUser = useSyncExternalStore(
    subscribeAuth,
    getAuthUserSnapshot,
    () => null,
  );
  const isOrgAdmin =
    currentUser?.role === 'admin' && currentUser?.is_demo !== true;

  const [teams, setTeams] = useState<TeamDTO[]>([]);
  const [users, setUsers] = useState<UserSummaryDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  // Add Team inline form state
  const [teamId, setTeamId] = useState('');
  const [teamDisplayName, setTeamDisplayName] = useState('');
  const [teamDescription, setTeamDescription] = useState('');
  const [creatingTeam, setCreatingTeam] = useState(false);
  const [teamError, setTeamError] = useState<string | null>(null);

  // Add Member modal state
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<ActorRole>('operator');
  const [newTeams, setNewTeams] = useState<string[]>(['*']);
  const [creatingUser, setCreatingUser] = useState(false);
  const [userModalError, setUserModalError] = useState<string | null>(null);

  // Edit User modal state
  const [editingUser, setEditingUser] = useState<UserSummaryDTO | null>(null);
  const [editRole, setEditRole] = useState<ActorRole>('operator');
  const [editTeams, setEditTeams] = useState<string[]>(['*']);
  const [savingEdit, setSavingEdit] = useState(false);

  const loadData = useCallback(async () => {
    if (!isOrgAdmin) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [teamList, userList] = await Promise.all([
        fetchTeams(),
        fetchUsers(),
      ]);
      setTeams(teamList);
      setUsers(userList);
      setPageError(null);
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to load users and teams',
      );
    } finally {
      setLoading(false);
    }
  }, [isOrgAdmin]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (creatingTeam) return;
    setCreatingTeam(true);
    setTeamError(null);
    try {
      const created = await createTeam({
        team_id: teamId.trim(),
        display_name: teamDisplayName.trim(),
        description: teamDescription.trim() || null,
      });
      setTeams((prev) =>
        [...prev, created].sort((a, b) =>
          a.display_name.localeCompare(b.display_name),
        ),
      );
      setTeamId('');
      setTeamDisplayName('');
      setTeamDescription('');
    } catch (err: unknown) {
      setTeamError(
        err instanceof Error ? err.message : 'Failed to create team',
      );
    } finally {
      setCreatingTeam(false);
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (creatingUser) return;
    if (newTeams.length === 0) {
      setUserModalError('Select All Teams (*) or at least one team.');
      return;
    }
    setCreatingUser(true);
    setUserModalError(null);
    try {
      const created = await createUser({
        display_name: newName.trim(),
        email: newEmail.trim().toLowerCase(),
        password: newPassword,
        role: newRole,
        allowed_teams: newTeams,
      });
      setUsers((prev) => [...prev, created]);
      setAddOpen(false);
      setNewName('');
      setNewEmail('');
      setNewPassword('');
      setNewRole('operator');
      setNewTeams(['*']);
    } catch (err: unknown) {
      setUserModalError(
        err instanceof Error ? err.message : 'Failed to provision user',
      );
    } finally {
      setCreatingUser(false);
    }
  };

  const openEditUser = (user: UserSummaryDTO) => {
    setUserModalError(null);
    setEditingUser(user);
    setEditRole((user.role as ActorRole) || 'operator');
    setEditTeams(user.allowed_teams.length > 0 ? user.allowed_teams : ['*']);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser || savingEdit) return;
    if (editTeams.length === 0) {
      setUserModalError('Select All Teams (*) or at least one team.');
      return;
    }
    setSavingEdit(true);
    setUserModalError(null);
    try {
      const updated = await updateUser(editingUser.user_id, {
        role: editRole,
        allowed_teams: editTeams,
      });
      setUsers((prev) =>
        prev.map((u) => (u.user_id === updated.user_id ? updated : u)),
      );
      setEditingUser(null);
    } catch (err: unknown) {
      setUserModalError(
        err instanceof Error ? err.message : 'Failed to update user',
      );
    } finally {
      setSavingEdit(false);
    }
  };

  const handleToggleActive = async (user: UserSummaryDTO) => {
    try {
      const updated = await updateUser(user.user_id, {
        is_active: !user.is_active,
      });
      setUsers((prev) =>
        prev.map((u) => (u.user_id === updated.user_id ? updated : u)),
      );
      setPageError(null);
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to update user status',
      );
    }
  };

  if (mounted && currentUser && !isOrgAdmin) {
    return (
      <div className="rounded-xl border border-amber-300 dark:border-amber-700/60 bg-white dark:bg-[#07152E] p-8 max-w-xl">
        <div className="flex items-start gap-3">
          <Shield className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Administrator Access Required
            </h2>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
              Only non-demo organization administrators can view and manage provisioned users and departments.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {pageError && (
        <div className="rounded-lg border border-red-200 dark:border-red-800/70 bg-red-50 dark:bg-red-950/60 px-4 py-3 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{pageError}</span>
        </div>
      )}

      {/* Section 1: Organizational Teams */}
      <section className="rounded-xl border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shadow-sm">
        <div className="border-b border-slate-200 dark:border-[#172E56] px-5 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <Building2
              className="h-4 w-4 text-[#0257D5] dark:text-[#00C2FF]"
              aria-hidden="true"
            />
            <div>
              <h2 className="text-sm font-semibold text-[#041533] dark:text-slate-100">
                Organizational Teams
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Departments used to scope agent telemetry, policies, and user access.
              </p>
            </div>
          </div>
          <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
            {teams.length} teams
          </span>
        </div>

        <div className="p-5 space-y-5">
          {loading ? (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Loading organizational teams...
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              {teams.map((team) => (
                <div
                  key={team.team_id}
                  className="rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-[#F5F9FF]/60 dark:bg-[#0A1B3B] p-3.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-[#041533] dark:text-slate-100 truncate">
                      {team.display_name}
                    </span>
                  </div>
                  <span className="mt-1 inline-block rounded border border-slate-200 dark:border-[#1D3868] bg-white dark:bg-[#07152E] px-1.5 py-0.5 text-[11px] font-mono text-[#0257D5] dark:text-[#7DD3FC]">
                    {team.team_id}
                  </span>
                  {team.description && (
                    <p className="mt-2 text-xs text-slate-600 dark:text-slate-400 line-clamp-2">
                      {team.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          <form
            onSubmit={handleCreateTeam}
            className="rounded-lg border border-dashed border-[#D4E2F4] dark:border-[#1D3868] bg-slate-50/70 dark:bg-[#040B18]/60 p-4"
          >
            <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 mb-3">
              Add Department
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                required
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                placeholder="team_id (e.g. payments-risk)"
                aria-label="Team ID"
                className="rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs font-mono text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
              />
              <input
                type="text"
                required
                value={teamDisplayName}
                onChange={(e) => setTeamDisplayName(e.target.value)}
                placeholder="Display Name (e.g. Payments Risk)"
                aria-label="Team Display Name"
                className="rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  value={teamDescription}
                  onChange={(e) => setTeamDescription(e.target.value)}
                  placeholder="Description (optional)"
                  aria-label="Team Description"
                  className="flex-1 min-w-0 rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={creatingTeam}
                  className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-3.5 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50 transition-colors whitespace-nowrap shrink-0"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{creatingTeam ? 'Adding...' : 'Add Team'}</span>
                </button>
              </div>
            </div>
            {teamError && (
              <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                {teamError}
              </p>
            )}
          </form>
        </div>
      </section>

      {/* Section 2: Provisioned Users */}
      <section className="rounded-xl border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shadow-sm">
        <div className="border-b border-slate-200 dark:border-[#172E56] px-5 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <Users
              className="h-4 w-4 text-[#0257D5] dark:text-[#00C2FF]"
              aria-hidden="true"
            />
            <div>
              <h2 className="text-sm font-semibold text-[#041533] dark:text-slate-100">
                Provisioned Users
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Organization members with RBAC roles and team access scopes.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setUserModalError(null);
              setAddOpen(true);
            }}
            className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-3.5 py-2 text-xs font-medium text-white hover:bg-[#0346B0] transition-colors whitespace-nowrap"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Add Team Member</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-[#172E56] bg-slate-50/70 dark:bg-[#040B18] text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                <th className="px-5 py-3">Member</th>
                <th className="px-5 py-3">Email</th>
                <th className="px-5 py-3">Role</th>
                <th className="px-5 py-3">Allowed Teams</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-[#172E56] text-xs">
              {loading ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-5 py-8 text-center text-slate-500 dark:text-slate-400"
                  >
                    Loading provisioned users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-5 py-8 text-center text-slate-500 dark:text-slate-400"
                  >
                    No organization members provisioned yet.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr
                    key={u.user_id}
                    className="hover:bg-[#F5F9FF]/60 dark:hover:bg-[#0A1B3B]/60 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <p className="font-medium text-slate-900 dark:text-slate-100">
                        {u.display_name}
                      </p>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        Added {formatRelativeTime(u.created_at)}
                      </p>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-700 dark:text-slate-300">
                      {u.email}
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={cn(
                          'inline-flex rounded border px-2 py-0.5 text-[11px] font-mono font-medium',
                          roleBadgeClasses(u.role),
                        )}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {u.allowed_teams.map((team) => (
                          <span
                            key={team}
                            className="rounded border border-slate-200 dark:border-[#1D3868] bg-slate-50 dark:bg-[#0A1B3B] px-1.5 py-0.5 text-[11px] font-mono text-slate-700 dark:text-slate-300"
                          >
                            {team === '*' ? 'All Teams (*)' : team}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      {u.is_active ? (
                        <span className="inline-flex items-center gap-1 rounded border border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          <span>Active</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-400">
                          <XCircle className="h-3 w-3" aria-hidden="true" />
                          <span>Deactivated</span>
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => openEditUser(u)}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2.5 py-1 text-[11px] font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650] transition-colors"
                        >
                          <Pencil className="h-3 w-3" aria-hidden="true" />
                          <span>Edit</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleToggleActive(u)}
                          className={cn(
                            'rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors',
                            u.is_active
                              ? 'border-red-200 text-red-700 hover:bg-red-50 dark:border-red-800/60 dark:text-red-300 dark:hover:bg-red-950/50'
                              : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800/60 dark:text-emerald-300 dark:hover:bg-emerald-950/50',
                          )}
                        >
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Add Team Member Modal */}
      {mounted &&
        addOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setAddOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="add-member-title"
              className="w-full max-w-md rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <h3
                  id="add-member-title"
                  className="text-base font-semibold text-slate-900 dark:text-slate-100"
                >
                  Add Team Member
                </h3>
                <button
                  type="button"
                  onClick={() => setAddOpen(false)}
                  className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleCreateUser} className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Display Name
                  </label>
                  <input
                    type="text"
                    required
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Maya Patel"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Work Email
                  </label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="maya@company.com"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Temporary Password
                  </label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Initial password"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    RBAC Role
                  </label>
                  <select
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value as ActorRole)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  >
                    {ROLE_OPTIONS.map((roleOpt) => (
                      <option key={roleOpt} value={roleOpt}>
                        {roleOpt}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Allowed Teams
                  </p>
                  <TeamScopeSelector
                    teams={teams}
                    selected={newTeams}
                    onChange={setNewTeams}
                  />
                </div>

                {userModalError && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {userModalError}
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-[#172E56]">
                  <button
                    type="button"
                    onClick={() => setAddOpen(false)}
                    className="rounded-md border border-slate-300 dark:border-[#1D3868] px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creatingUser}
                    className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50"
                  >
                    {creatingUser ? 'Provisioning...' : 'Provision Member'}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body,
        )}

      {/* Edit User Modal */}
      {mounted &&
        editingUser &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setEditingUser(null)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="edit-member-title"
              className="w-full max-w-md rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <div>
                  <h3
                    id="edit-member-title"
                    className="text-base font-semibold text-slate-900 dark:text-slate-100"
                  >
                    Edit Member Access
                  </h3>
                  <p className="text-xs font-mono text-slate-500 dark:text-slate-400">
                    {editingUser.email}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingUser(null)}
                  className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleSaveEdit} className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    RBAC Role
                  </label>
                  <select
                    value={editRole}
                    onChange={(e) => setEditRole(e.target.value as ActorRole)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  >
                    {ROLE_OPTIONS.map((roleOpt) => (
                      <option key={roleOpt} value={roleOpt}>
                        {roleOpt}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Allowed Teams
                  </p>
                  <TeamScopeSelector
                    teams={teams}
                    selected={editTeams}
                    onChange={setEditTeams}
                  />
                </div>

                {userModalError && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {userModalError}
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-[#172E56]">
                  <button
                    type="button"
                    onClick={() => setEditingUser(null)}
                    className="rounded-md border border-slate-300 dark:border-[#1D3868] px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={savingEdit}
                    className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50"
                  >
                    {savingEdit ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

