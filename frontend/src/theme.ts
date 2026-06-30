import { createTheme, type MantineColorsTuple } from "@mantine/core";

const ditto: MantineColorsTuple = [
  "#f6ecff",
  "#e6d2ff",
  "#d2b2ff",
  "#be90fb",
  "#b275f5",
  "#ab63f2", // brand — primaryShade
  "#9a4ee6",
  "#8438cc",
  "#6f2bb0",
  "#571f8c",
];

export const theme = createTheme({
  primaryColor: "ditto",
  primaryShade: { light: 5, dark: 5 },
  colors: { ditto },
  fontFamily: '"Hanken Grotesk", system-ui, sans-serif',
  fontFamilyMonospace: '"Space Mono", ui-monospace, monospace',
  defaultRadius: "lg",
  headings: {
    fontFamily: '"Syne", "Hanken Grotesk", sans-serif',
    fontWeight: "800",
  },
  components: {
    Button: {
      defaultProps: { radius: "md" },
    },
    Input: {
      defaultProps: { radius: "md" },
    },
  },
});
