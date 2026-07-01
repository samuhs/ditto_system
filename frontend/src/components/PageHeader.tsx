interface PageHeaderProps {
  eyebrow: string;
  title: string;
  subtitle?: string;
}

export function PageHeader({ eyebrow, title, subtitle }: PageHeaderProps) {
  return (
    <header className="ditto-page-head">
      <div className="ditto-eyebrow">{eyebrow}</div>
      <h1 className="ditto-page-title">{title}</h1>
      {subtitle && <p className="ditto-page-sub">{subtitle}</p>}
    </header>
  );
}
