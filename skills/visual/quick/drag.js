// Inlined by render.mjs when a page has a diagram. Mouse click-and-drag scrolls a wide diagram.
// Touch already scrolls natively, so only the mouse is handled. No network, no dependencies.
const overflows = (box) => box.scrollWidth > box.clientWidth + 1 || box.scrollHeight > box.clientHeight + 1;
for (const box of document.querySelectorAll(".diagram")) {
  // re-checked whenever the box or window changes size, not only at load
  const mark = () => box.classList.toggle("draggable", overflows(box));
  mark();
  if (window.ResizeObserver) new ResizeObserver(mark).observe(box);
  else window.addEventListener("resize", mark);
  let start = null;
  box.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" || e.button !== 0 || !overflows(box)) return;
    e.preventDefault();                       // no text selection or native image drag
    start = { x: e.clientX, y: e.clientY, left: box.scrollLeft, top: box.scrollTop };
    try { box.setPointerCapture(e.pointerId); } catch {}
    box.classList.add("dragging");
  });
  box.addEventListener("pointermove", (e) => {
    if (!start) return;
    box.scrollLeft = start.left - (e.clientX - start.x);
    box.scrollTop = start.top - (e.clientY - start.y);
  });
  const stop = () => { start = null; box.classList.remove("dragging"); };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  box.addEventListener("lostpointercapture", stop);
  box.addEventListener("dragstart", (e) => e.preventDefault());
}
