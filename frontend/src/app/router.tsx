import { createBrowserRouter } from "react-router-dom";

import { FoundationPage } from "@/features/foundation/FoundationPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <FoundationPage />,
  },
]);
