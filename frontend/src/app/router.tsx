import { createBrowserRouter } from "react-router-dom";

import { AuthGate } from "@/features/auth/AuthGate";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AuthGate />,
  },
]);
