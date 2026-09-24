const display = document.getElementById("display");
const buttons = document.querySelectorAll("button");

let expression = "";

function updateDisplay(value) {
  display.value = value || "0";
}

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    const value = button.dataset.value;
    const action = button.dataset.action;

    if (action === "clear") {
      expression = "";
      updateDisplay(expression);
      return;
    }

    if (action === "delete") {
      expression = expression.slice(0, -1);
      updateDisplay(expression);
      return;
    }

    if (action === "equals") {
      if (!expression) return;

      try {
        const result = Function(`"use strict"; return (${expression})`)();

        if (!Number.isFinite(result)) {
          throw new Error("Invalid result");
        }

        expression = String(result);
        updateDisplay(expression);
      } catch {
        expression = "";
        updateDisplay("Error");
      }

      return;
    }

    expression += value;
    updateDisplay(expression);
  });
});
