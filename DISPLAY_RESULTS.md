# How to Display Results

You have multiple ways to display and present your evaluation results:

## 1. Console Display (Formatted Text)

Display results in a nicely formatted console output:

```bash
# Display latest results
python display_results.py --latest

# Display specific result files
python display_results.py --degradation results/degradation_20251204_235444.json --explainability results/explainability_20251204_235444.json

# Show only summary
python display_results.py --latest --summary-only
```

**Features:**
- ✅ Formatted tables
- ✅ Visual progress bars
- ✅ Detailed breakdowns
- ✅ Color-coded output

## 2. HTML Report (Web Browser)

Generate a beautiful HTML report that you can open in any browser:

```bash
# Generate HTML from latest results
python generate_html_report.py --latest

# Generate HTML from specific files
python generate_html_report.py --degradation results/degradation_XXX.json --explainability results/explainability_XXX.json

# Custom output filename
python generate_html_report.py --latest --output my_report.html
```

Then open `evaluation_report.html` in your browser!

**Features:**
- ✅ Professional styling
- ✅ Interactive tables
- ✅ Visual progress bars
- ✅ Print-friendly
- ✅ Shareable (just send the HTML file)

## 3. JSON Files (Programmatic Access)

All results are automatically saved as JSON files in the `results/` directory:

- `degradation_YYYYMMDD_HHMMSS.json` - Skill degradation test results
- `explainability_YYYYMMDD_HHMMSS.json` - Explainability test results  
- `summary_YYYYMMDD_HHMMSS.json` - Combined summary

You can:
- Load these in Python for further analysis
- Import into Excel/Google Sheets
- Use for custom visualizations
- Share with your professor

## 4. Quick Summary from Command Line

The `run_evaluations.py` script also prints a summary:

```bash
python run_evaluations.py --all
```

## Recommended Workflow

1. **Run the tests:**
   ```bash
   python run_evaluations.py --all
   ```

2. **Generate HTML report:**
   ```bash
   python generate_html_report.py --latest
   ```

3. **Open the HTML file in your browser** to review

4. **For presentations, use the console display:**
   ```bash
   python display_results.py --latest
   ```

## What Each Display Shows

### Skill Degradation Test:
- Original candidate information
- Degradation sequence steps
- Score decay table
- Visual score decay bars
- Summary metrics (final score, drop percentage, critical point)

### Explainability Test:
- Overall metrics (mention rates, alignment score)
- Visual progress bars
- Detailed results for each candidate pair:
  - Scoring breakdown (Jaccard, Guttman)
  - Recruiter Agent explanation
  - Validation results
  - Alignment scores

## Tips for Your Presentation

1. **Start with the HTML report** - It's the most professional looking
2. **Use console display** for live demos or terminal presentations
3. **Reference JSON files** for specific numbers or data points
4. **Show the visual score decay** - It's very impactful
5. **Highlight the 100% mention rates** - Shows excellent explainability

## Example Output Locations

All results are saved to:
- Console: Terminal output
- HTML: `evaluation_report.html` (in project root)
- JSON: `results/` directory

