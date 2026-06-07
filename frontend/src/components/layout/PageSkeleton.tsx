import "./PageSkeleton.css";

export function PageSkeleton() {
  return (
    <div className="page-skeleton">
      <div className="page-skeleton__header">
        <div className="page-skeleton__title" />
        <div className="page-skeleton__subtitle" />
      </div>
      <div className="page-skeleton__body">
        <div className="page-skeleton__row">
          <div className="page-skeleton__card" />
          <div className="page-skeleton__card" />
        </div>
        <div className="page-skeleton__row">
          <div className="page-skeleton__card" />
          <div className="page-skeleton__card" />
        </div>
      </div>
    </div>
  );
}
