import './PageLayout.css';

function PageLayout({ children }) {
  return <main className="page">{children}</main>;
}

export default PageLayout;