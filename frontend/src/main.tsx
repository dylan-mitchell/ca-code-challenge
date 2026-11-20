import "vite/modulepreload-polyfill";
import { createRoot } from "react-dom/client";
import { BrandList } from "./BrandList";

const container = document.getElementById("brand-list");
if (container) {
  createRoot(container).render(<BrandList />);
}
