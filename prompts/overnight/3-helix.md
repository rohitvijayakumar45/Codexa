3. HELIX — Full-Stack Research Workspace

Build HELIX, a full-stack collaborative research and knowledge-management application for teams conducting long-running research projects.

This is a full-stack benchmark. Build the frontend, backend, database, API layer, persistence, validation, and complete application behavior.

The product should allow teams to create research projects, collect sources, organize findings, write notes, create relationships between ideas, assign work, track progress, and maintain a persistent history of how the research evolved.

The application should have a sophisticated classical light design system rather than a conventional SaaS aesthetic: warm ivory, paper, charcoal, ink, restrained accent colors, editorial typography, precise spacing, elegant dividers, subtle depth, and restrained motion.

The core experience should revolve around a research workspace where users can move between:

projects
research notes
sources
findings
people/contributors
tasks
relationships
timelines
project activity

Design the information architecture yourself. The objective is to test product and engineering judgment rather than following a rigid screen specification.

The application must have real persistence.

Users should be able to create and edit research projects, notes, sources, findings, tasks, and relationships. Changes must survive reloads and be represented correctly in the database.

Create a proper relational data model and clean API architecture.

Important interactions should include things such as:

creating and editing research material
linking related information
assigning tasks
changing task states
filtering and searching
opening detailed records
adding notes/comments
viewing activity/history
navigating relationships
tracking project progress

Implement appropriate validation, loading states, optimistic interactions where sensible, error handling, empty states, and recovery behavior.

Create at least one signature interaction around the research graph or knowledge structure. It should allow users to understand relationships between information without becoming a gimmicky visualization.

The interface should feel highly polished and fluid. Use smooth scrolling, thoughtful transitions, subtle micro-interactions, meaningful motion, and elegant state changes while keeping the classical design language intact.

The application should feel credible with realistic seed data from the moment it launches.

Build the frontend and backend as a coherent system rather than treating the backend as an afterthought.

Include:

database schema
persistence
API endpoints
frontend state management
validation
error handling
realistic seeded data
responsive design
accessibility
meaningful empty/loading/error states
end-to-end tests for important workflows

After the first implementation, actually run the complete application.

Test the important flows end to end.

Then visually inspect the frontend and refine it repeatedly. Look for weak hierarchy, generic components, poor spacing, awkward transitions, broken responsive behavior, inconsistent states, and anything that feels unfinished.

Do not stop after the first successful build or after the backend works.

The final result should feel like a serious commercial research platform with an unusually refined visual identity.
