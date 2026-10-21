
# Flow A — Usage Data Schema

## Purpose
Define a consistent input format for customer usage health monitoring.

## Source
SocialPeta usage export files (Excel).
The first version uses locally provided files or simulated data.

## Source Fields
- company_id
- company_name
- user_id
- user_email
- platform_frequency_label
- usage_by_date
- date_coverage

## Data Rules
1. Preserve the original high/low-frequency label.
2. Preserve zero usage as zero.
3. Do not silently convert missing values to zero.
4. Record the actual date coverage of each file.
5. Exclude accounts without valid numeric usage data from
   quantitative health scoring.
6. Flag duplicate account records for review.
7. Do not infer company health from a single account alone.
8. Do not hard-code an unverified usage threshold.

## Privacy
- Real customer exports must not be committed to public GitHub.
- Use synthetic or anonymized data for public demonstrations.
- Keep customer emails out of demo logs and screenshots.

## Planned Outputs
- Normalized usage records
- Data quality warnings
- Account-level usage metrics
- Company-level usage summaries
- Health alerts with explicit reasons
