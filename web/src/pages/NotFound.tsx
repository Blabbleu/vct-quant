import { Link } from "react-router-dom";
import { PageHead } from "../components/ui";

export default function NotFound() {
  return <PageHead title="Page not found"><Link to="/">Back to the home page</Link></PageHead>;
}
