/* Label blocks without changing their code text. */
(() => {
  function labelBlocks() {
    document.querySelectorAll('.md-typeset .highlight').forEach(block => {
      const match = block.className.match(/(?:^|\s)language-([\w+-]+)/)
        || block.querySelector('code')?.className.match(/(?:^|\s)language-([\w+-]+)/);
      block.dataset.language = match ? match[1] : 'text';
    });
  }
  if (typeof document$ !== 'undefined') document$.subscribe(labelBlocks);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', labelBlocks);
  else labelBlocks();
})();
