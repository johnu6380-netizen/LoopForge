import { DataProvider } from "./data/DataContext";
import { Layout, NAV } from "./components/Layout";
import { useRoute } from "./lib/useHashRoute";
import { Overview } from "./pages/Overview";
import { Results } from "./pages/Results";
import { Explorer } from "./pages/Explorer";
import { Methods } from "./pages/Methods";

function Page({ route }: { route: string[] }) {
  switch (route[0] ?? "") {
    case "":
      return <Overview />;
    case "results":
      return <Results />;
    case "explorer":
      return <Explorer />;
    case "methods":
      return <Methods />;
    default:
      return (
        <>
          <h1>Page not found</h1>
          <p>
            There is no page at <code>{route.join("/")}</code>. Use the menu, or go back to the <a href="#/">overview</a>.
          </p>
        </>
      );
  }
}

export default function App() {
  const route = useRoute();
  const first = route[0] ?? "";
  const current = NAV.some((n) => n.path === first) ? first : "";
  return (
    <DataProvider>
      <Layout current={current}>
        <Page route={route} />
      </Layout>
    </DataProvider>
  );
}
