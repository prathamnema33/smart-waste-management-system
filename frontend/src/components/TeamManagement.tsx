"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Team, TeamOptions } from "@/lib/types";

export default function TeamManagement({
  onTeamCreated,
}: {
  onTeamCreated: () => void;
}) {
  const [options, setOptions] = useState<TeamOptions | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [areaId, setAreaId] = useState("");
  const [teamName, setTeamName] = useState("");
  const [workerIds, setWorkerIds] = useState<number[]>([]);
  const [leaderId, setLeaderId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([api.teamOptions(), api.teams()])
      .then(([teamOptions, teamList]) => {
        if (active) {
          setOptions(teamOptions);
          setTeams(teamList);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load team data.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [retry]);

  const availableAreas = useMemo(
    () => options?.areas.filter((area) => !area.has_team) ?? [],
    [options],
  );
  const availableWorkers = useMemo(
    () =>
      options?.workers.filter(
        (worker) => worker.area_id === Number(areaId) && worker.team_id === null,
      ) ?? [],
    [areaId, options],
  );
  const availableVehicles = useMemo(
    () =>
      options?.vehicles.filter((vehicle) =>
        vehicleCanBeAssigned(vehicle.status),
      ) ?? [],
    [options],
  );

  function toggleWorker(workerId: number) {
    const next = workerIds.includes(workerId)
      ? workerIds.filter((id) => id !== workerId)
      : [...workerIds, workerId];
    setWorkerIds(next);
    if (!next.includes(Number(leaderId))) setLeaderId("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const created = await api.createTeam({
        team_name: teamName,
        area_id: Number(areaId),
        leader_worker_id: Number(leaderId),
        worker_ids: workerIds,
        vehicle_id: vehicleId ? Number(vehicleId) : null,
      });
      setTeams((current) => [...current, created]);
      setOptions((current) =>
        current
          ? {
              ...current,
              areas: current.areas.map((area) =>
                area.area_id === created.area_id ? { ...area, has_team: true } : area,
              ),
            }
          : current,
      );
      setAreaId("");
      setTeamName("");
      setWorkerIds([]);
      setLeaderId("");
      setVehicleId("");
      setMessage(
        created.zone_boundary
          ? "Team created and its zone boundary calculated from available geographic points."
          : "Team created. No geographic points are available yet to draw its zone.",
      );
      onTeamCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create team.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section className="panel team-management-panel">
        <div className="loading-line">
          <div className="spinner" />
          Loading teams and area assignments...
        </div>
      </section>
    );
  }

  if (error && !options) {
    return (
      <section className="panel team-management-panel">
        <div className="segregation-map-error" role="alert">
          <span>{error}</span>
          <button
            className="text-button"
            onClick={() => {
              setLoading(true);
              setError(null);
              setRetry((value) => value + 1);
            }}
          >
            Try again
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="panel team-management-panel">
      <div className="section-title">
        <div>
          <p className="eyebrow">Area operations</p>
          <h2>Create an area team</h2>
          <p className="muted team-management-subtitle">
            Assign available area workers and a team vehicle. Zone bounds are calculated from
            recorded area, report, and latest vehicle GPS coordinates.
          </p>
        </div>
      </div>

      {error && <div className="error-box team-form-message" role="alert">{error}</div>}
      {message && <div className="team-success-message" role="status">{message}</div>}

      <form className="team-create-form" onSubmit={submit}>
        <label>
          Team name
          <input
            value={teamName}
            onChange={(event) => setTeamName(event.target.value)}
            maxLength={100}
            placeholder="North Zone Team"
            required
          />
        </label>
        <label>
          Area
          <select
            value={areaId}
            onChange={(event) => {
              setAreaId(event.target.value);
              setWorkerIds([]);
              setLeaderId("");
              setVehicleId("");
            }}
            required
          >
            <option value="">Select an available area</option>
            {availableAreas.map((area) => (
              <option key={area.area_id} value={area.area_id}>
                {area.area_name}
              </option>
            ))}
          </select>
        </label>

        <fieldset className="team-worker-selection">
          <legend>Workers in selected area</legend>
          {areaId && availableWorkers.length === 0 ? (
            <p className="muted">No unassigned workers are available in this area.</p>
          ) : areaId ? (
            availableWorkers.map((worker) => (
              <label className="team-worker-option" key={worker.worker_id}>
                <input
                  type="checkbox"
                  checked={workerIds.includes(worker.worker_id)}
                  onChange={() => toggleWorker(worker.worker_id)}
                />
                <span>{worker.worker_name}</span>
              </label>
            ))
          ) : (
            <p className="muted">Select an area to see its available workers.</p>
          )}
        </fieldset>

        <label>
          Team leader
          <select
            value={leaderId}
            onChange={(event) => setLeaderId(event.target.value)}
            disabled={!workerIds.length}
            required
          >
            <option value="">Select a team member</option>
            {availableWorkers
              .filter((worker) => workerIds.includes(worker.worker_id))
              .map((worker) => (
                <option key={worker.worker_id} value={worker.worker_id}>
                  {worker.worker_name}
                </option>
              ))}
          </select>
        </label>

        <label>
          Assigned vehicle
          <select
            value={vehicleId}
            onChange={(event) => setVehicleId(event.target.value)}
            disabled={!workerIds.length}
          >
            <option value="">No vehicle assigned</option>
            {availableVehicles.map((vehicle) => (
              <option key={vehicle.vehicle_id} value={vehicle.vehicle_id}>
                {vehicle.vehicle_number} — {vehicle.worker_name}
                {vehicle.team_ids.length > 0
                  ? ` · already assigned to ${vehicle.team_ids.length} team${vehicle.team_ids.length === 1 ? "" : "s"}`
                  : ""}
              </option>
            ))}
          </select>
        </label>

        <button
          className="primary-button team-submit-button"
          disabled={saving || !areaId || !workerIds.length || !leaderId}
        >
          {saving ? "Creating team..." : "Create team"}
        </button>
      </form>

      <div className="team-existing-list">
        <h3>Existing teams</h3>
        {teams.length ? (
          teams.map((team) => (
            <div className="team-existing-row" key={team.team_id}>
              <div>
                <strong>{team.team_name}</strong>
                <small>
                  {team.area_name} · Leader: {team.leader_name} · {team.worker_count} workers
                </small>
              </div>
              <span className="pill">
                {team.zone_boundary ? "Zone mapped" : "No coordinates yet"}
              </span>
            </div>
          ))
        ) : (
          <p className="muted">No teams have been created.</p>
        )}
      </div>
    </section>
  );
}

function vehicleCanBeAssigned(status: string | null) {
  return (
    status === null ||
    ["ACTIVE", "AVAILABLE", "ASSIGNED", "IN_SERVICE"].includes(status)
  );
}
