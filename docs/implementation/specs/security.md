# Security Spec

Relevant rules for this project (internal university simulation, no auth, no users).

## SQL Injection Prevention
- Always use parameterized queries (never string concatenation)
  ```python
  # GOOD
  conn.execute("SELECT * FROM flights WHERE id = ?", (flight_id,))
  # BAD
  conn.execute(f"SELECT * FROM flights WHERE id = '{flight_id}'")
  ```

## Path Traversal (File Serving)
- Validate requested file paths stay within the allowed output directory
  ```python
  real_path = os.path.realpath(requested_path)
  if not real_path.startswith(os.path.realpath(OUTPUT_ROOT)):
      raise HTTPException(403, "Access denied")
  ```

## Subprocess Safety
- Never pass user input directly to subprocess/shell commands
- Use list-form arguments with subprocess.Popen, not shell=True

## Error Responses
- Don't expose full stack traces or file paths in API error responses
- Log detailed errors server-side, return generic messages to client

That's it. No auth, no CORS restrictions, no rate limiting, no encryption needed for this project.
