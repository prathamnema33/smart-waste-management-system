CREATE TABLE teams (
    team_id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    area_id INTEGER NOT NULL REFERENCES areas(area_id),
    leader_worker_id INTEGER NOT NULL REFERENCES workers(worker_id),
    vehicle_id INTEGER REFERENCES vehicles(vehicle_id),
    min_latitude NUMERIC(9, 6),
    max_latitude NUMERIC(9, 6),
    min_longitude NUMERIC(9, 6),
    max_longitude NUMERIC(9, 6),
    CONSTRAINT uq_teams_area UNIQUE (area_id),
    CONSTRAINT uq_teams_vehicle UNIQUE (vehicle_id)
);

CREATE TABLE team_members (
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    worker_id INTEGER NOT NULL REFERENCES workers(worker_id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, worker_id),
    CONSTRAINT uq_team_members_worker UNIQUE (worker_id)
);

CREATE INDEX ix_waste_reports_area_coordinates
    ON waste_reports (area_id, latitude, longitude);

CREATE INDEX ix_vehicle_locations_vehicle_time
    ON vehicle_locations (vehicle_id, recorded_at DESC, location_id DESC);
