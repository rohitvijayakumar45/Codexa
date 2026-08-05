// Ensure uniqueness on stable_id for all specific node types
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Repository) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:File) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:CodeSymbol) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ApiRoute) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:SchemaField) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ExternalArtifact) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ArchitectureTrend) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:SimulationScenario) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:CausalEvent) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Decision) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Tradeoff) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:RejectedAlternative) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:OnboardingPath) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:HealthMetric) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:PreventionRule) REQUIRE n.stable_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ConventionProfile) REQUIRE n.stable_id IS UNIQUE;

// Indexes for temporal queries on edges (valid_from, valid_to) 
CREATE INDEX IF NOT EXISTS FOR ()-[r:calls]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:imports]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:depends_on]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:causes]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:mitigates]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:increases_risk_of]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:correlates_with]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:derived_from]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:supersedes]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:flows_into]-() ON (r.valid_from, r.valid_to);
CREATE INDEX IF NOT EXISTS FOR ()-[r:traces_to_decision]-() ON (r.valid_from, r.valid_to);

// Index on confidence for probabilistic edges
CREATE INDEX IF NOT EXISTS FOR ()-[r:causes]-() ON (r.confidence);
CREATE INDEX IF NOT EXISTS FOR ()-[r:increases_risk_of]-() ON (r.confidence);
CREATE INDEX IF NOT EXISTS FOR ()-[r:correlates_with]-() ON (r.confidence);
