/** Lifecycle spies only. Native focus/inert behavior must be checked in a browser. */
export function installDialogLifecycleStub() {
  const createElement = document.createElement;
  document.createElement = function (...args) {
    const element = createElement.apply(this, args);
    if (String(args[0]).toLowerCase() === 'dialog') {
      element.open = false;
      element.modalRequests = 0;
      element.closeRequests = 0;
      element.showModal = function () { this.open = true; this.modalRequests++; };
      element.close = function () { this.open = false; this.closeRequests++; };
    }
    return element;
  };
  return () => { document.createElement = createElement; };
}
