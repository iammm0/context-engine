import { create } from "zustand"

interface UiState {
  activeConversationId?: string
  selectedKnowledgeSpaceId?: string
  enableRag: boolean
  setActiveConversationId: (value?: string) => void
  setSelectedKnowledgeSpaceId: (value?: string) => void
  setEnableRag: (value: boolean) => void
}

export const useUiStore = create<UiState>((set) => ({
  activeConversationId: undefined,
  selectedKnowledgeSpaceId: undefined,
  enableRag: true,
  setActiveConversationId: (value) => set({ activeConversationId: value }),
  setSelectedKnowledgeSpaceId: (value) => set({ selectedKnowledgeSpaceId: value }),
  setEnableRag: (value) => set({ enableRag: value }),
}))
