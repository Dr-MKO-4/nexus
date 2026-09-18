import { create } from "zustand";

import type { Agent } from "@/types";

interface AgentState {
  /** "dict par nom" (spec)  Record plutôt qu'un tableau : accès O(1) par
   * nom d'agent, cohérent avec le fait qu'il n'y a qu'un nombre fixe et
   * connu d'agents (8, voir backend/api/routes/agents.py). */
  agents: Record<string, Agent>;
  updating: boolean;
  setAgents: (agents: Agent[]) => void;
  updateAgent: (agent: Agent) => void;
  setUpdating: (updating: boolean) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: {},
  updating: false,

  setAgents: (agents) => set({ agents: Object.fromEntries(agents.map((agent) => [agent.name, agent])) }),

  updateAgent: (agent) =>
    set((state) => ({ agents: { ...state.agents, [agent.name]: agent } })),

  setUpdating: (updating) => set({ updating }),
}));
