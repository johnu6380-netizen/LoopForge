export function Methods() {
  return (
    <>
      <h1>Methods and limitations</h1>
      <p className="lede">How the experiment was run, what the numbers mean, and what they cannot show.</p>

      <h2>The loop</h2>
      <p>
        Each experiment starts from a nearest-neighbour tour builder (the seed). In every turn a language model is shown the task, the rules and
        the best programs found so far, and replies with a complete Python program. The program is run in a sandbox on 12 development instances
        (4 each of 25, 50 and 100 cities, 10 s limit per instance). If it is valid and scores better than the best so far, it becomes the new best.
        Each turn was a fresh chat with memory and code execution off, but the prompt carried the archive forward, so the six turns are chained.
      </p>

      <h2>The score</h2>
      <p>
        Fitness is the mean of (tour length ÷ length of a plain 2-opt tour) over the instances. Lower is better; 1.0000 ties 2-opt. Any invalid
        instance makes the whole program invalid. The development set guided the search. A separate set of 12 held-out test instances was scored
        once, on the final best program only.
      </p>

      <h2>Baselines</h2>
      <ul>
        <li><strong>2-opt</strong>: the reference, 1.0000 by definition.</li>
        <li><strong>Nearest neighbour</strong>: the seed, about 1.15 on both sets.</li>
        <li><strong>Blind mutation</strong>: 9,000 random edits to the seed produced 0 improvements, so improvement here is not easy to get by chance.</li>
      </ul>

      <h2>How the data is checked</h2>
      <p>
        <code>npm run validate</code> re-derives every tour's validity, length, ratio and fitness from the stored points, compares headline numbers
        with the finalize output, and verifies the SHA-256 of every saved prompt, reply and program. It never runs candidate code. The explorer
        repeats the tour recomputation, and the file hash check, in your browser.
      </p>

      <h2>Limitations</h2>
      <ul>
        <li><strong>One run per model.</strong> The gap between 0.9513 and 0.9440 on test is small and could be noise. It is suggestive, not conclusive.</li>
        <li><strong>Different compute.</strong> Claude’s programs ran for a fixed 3–6 s time budget per instance; GPT’s finished in well under a second. Claude’s results also depend on wall-clock time, so they may vary slightly between machines.</li>
        <li><strong>Small instances.</strong> 12 dev and 12 test instances, up to 100 cities. This says nothing about large problems.</li>
        <li><strong>Descriptions are not recorded.</strong> The saved replies lack the DESCRIPTION line, so none is shown rather than invented.</li>
        <li><strong>Model labels</strong> (“GPT-6”, “Sonnet 5.5”) are as typed by the experimenter.</li>
        <li><strong>Dry-run data</strong> from development was excluded.</li>
      </ul>
    </>
  );
}
