import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Mantine only needs one working ramp; the visible colour of controls comes
// from the section tokens in global.css (--sec / --on-sec), not from here.
const ink: MantineColorsTuple = [
  "#f4f3f0", "#e6e3dc", "#cfcbc2", "#b3aea3", "#8a877f",
  "#6e6c74", "#56545c", "#3a3940", "#252429", "#17161a",
];

export const theme = createTheme({
  primaryColor: "ink",
  primaryShade: 9,
  colors: { ink },
  black: "#17161a",
  fontFamily: '"Archivo", system-ui, sans-serif',
  fontFamilyMonospace: '"JetBrains Mono", ui-monospace, monospace',
  defaultRadius: 2,
  cursorType: "pointer",
  focusRing: "never",
  headings: {
    fontFamily: '"Archivo", system-ui, sans-serif',
    fontWeight: "700",
  },
  components: {
    Button: { defaultProps: { radius: 2 } },
    Input: { defaultProps: { radius: 2 } },
    Drawer: {
      defaultProps: {
        position: "right",
        size: "lg",
        overlayProps: { backgroundOpacity: 0.35 },
        transitionProps: { duration: 90, timingFunction: "steps(2)" },
      },
    },
    Loader: { defaultProps: { type: "dots", color: "ink" } },
  },
});
