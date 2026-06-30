import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

// Home route does not call the API, but other pages are imported by App.
vi.mock("./api/client");

function renderApp() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("App shell", () => {
  it("renders the home hero and primary navigation", async () => {
    renderApp();
    expect(await screen.findByText(/Vire especialista/i)).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: /navegação principal/i });
    // sidebar links to the three tools (scoped to the nav region)
    expect(within(nav).getByRole("link", { name: /inserir documentos/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^resultados$/i })).toBeInTheDocument();
  });
});
