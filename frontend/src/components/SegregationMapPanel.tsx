"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AreaSegregation, Team } from "@/lib/types";

const SegregationMap = dynamic(() => import("./SegregationMap"), {
  ssr: false,
  loading: () => (
    <div className="segregation-map-state">
      <div className="spinner" />
      Loading area map...
    </div>
  ),
});

export default function SegregationMapPanel({
  visible,
  refreshKey,
}: {
  visible: boolean;
  refreshKey: string;
}) {
  const [areas, setAreas] = useState<AreaSegregation[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!visible) return;
    let active = true;
    Promise.all([api.segregationByArea(), api.teams()])
      .then(([areaResult, teamResult]) => {
        if (active) {
          setAreas(areaResult);
          setTeams(teamResult);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load area segregation data.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshKey, retry, visible]);

  return (
    <section className="panel segregation-map-panel" hidden={!visible}>
      <div className="section-title">
        <div>
          <p className="eyebrow">Area analytics</p>
          <h2>Area-wise segregation performance</h2>
          <p className="muted segregation-map-subtitle">
            Geographic view of household waste segregation quality.
          </p>
        </div>
        <button
          className="text-button"
          disabled={loading}
          onClick={() => {
            setLoading(true);
            setError(null);
            setRetry((value) => value + 1);
          }}
        >
          Refresh map
        </button>
      </div>
      {loading ? (
        <div className="segregation-map-state">
          <div className="spinner" />
          Loading area segregation data...
        </div>
      ) : error ? (
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
      ) : areas.length === 0 && teams.length === 0 ? (
        <div className="empty-state">No area segregation data found.</div>
      ) : (
        <SegregationMap areas={areas} teams={teams} visible={visible} />
      )}
    </section>
  );
}
