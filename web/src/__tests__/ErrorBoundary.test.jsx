import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import ErrorBoundary from "../components/ErrorBoundary.jsx";

// ErrorBoundary is a class component, test that it renders children
describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    const { getByText } = render(
      <ErrorBoundary>
        <div>Hello World</div>
      </ErrorBoundary>
    );
    expect(getByText("Hello World")).toBeTruthy();
  });

  it("renders fallback UI when error is thrown", () => {
    const BadComponent = () => {
      throw new Error("Test error");
    };

    // Suppress console.error for this test
    const originalError = console.error;
    console.error = () => {};

    const { getByText } = render(
      <ErrorBoundary>
        <BadComponent />
      </ErrorBoundary>
    );

    console.error = originalError;

    // ErrorBoundary should render the fallback
    expect(getByText(/Error/i)).toBeTruthy();
  });
});
