/* The engine and fonts are served locally so formulas also work offline. */
window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true,
  },
  options: {
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex",
  },
  startup: {
    ready() {
      MathJax.startup.defaultReady();
      MathJax.startup.document.inputJax[0].preFilters.add(({ math }) => {
        // Imported assignments often use bare \\ between display equations.
        // MathJax 3 needs an environment to preserve those explicit line breaks.
        if (math.display && /\\\\/.test(math.math) && !/\\begin\s*\{/.test(math.math)) {
          const environment = /(^|[^\\])&/.test(math.math) ? "aligned" : "gathered";
          math.math = `\\begin{${environment}}${math.math}\\end{${environment}}`;
        }
      });
    },
    pageReady() {
      return MathJax.startup.defaultPageReady().then(() => {
        // Material emits this for both initial load and instant navigation.
        if (typeof document$ !== "undefined") {
          document$.subscribe(() => {
            MathJax.startup.promise = MathJax.startup.promise
              .then(() => {
                MathJax.typesetClear();
                MathJax.texReset();
                return MathJax.typesetPromise();
              })
              .catch((error) => console.error("Math rendering failed", error));
          });
        }
      });
    },
  },
};
