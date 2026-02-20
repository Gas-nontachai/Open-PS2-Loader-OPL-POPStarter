import { STATES } from "./constants.js";

export const store = {
  currentState: STATES.IDLE,
  activeController: null,
  isLoading: false,
  autoCandidates: [],
  artSourceChoices: [],
};
