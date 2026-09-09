import { forwardRef, type AnchorHTMLAttributes } from "react";

type DocumentLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
};

// Use this only when the next document must receive different response
// headers. A Next client transition cannot replace Permissions-Policy.
export const DocumentLink = forwardRef<HTMLAnchorElement, DocumentLinkProps>(
  function DocumentLink({ href, ...props }, ref) {
    return <a ref={ref} href={href} {...props} />;
  },
);
