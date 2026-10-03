import { useEffect, useRef } from 'react';

export default function Modal({ id, open, required = false, onDismiss, children }) {
  const dialog = useRef(null);
  useEffect(() => {
    const element = dialog.current;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);
  return (
    <dialog
      ref={dialog}
      id={id}
      onCancel={(event) => {
        if (required) event.preventDefault();
        else onDismiss();
      }}
    >
      {children}
    </dialog>
  );
}
