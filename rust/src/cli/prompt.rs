//! The four questions the CLI asks a person.
//!
//! `console` does the only hard part, which is reading a key without echoing it:
//! `tcsetattr` on Unix and `SetConsoleMode` on Windows. It costs nothing to use,
//! because `indicatif` already brings it for the spinner (§2.1c).
//!
//! **A prompt fails closed when there is no terminal.** Reading EOF in a loop
//! would hang a script for ever instead of telling it what is wrong, so a
//! missing terminal is a named error and a non-zero exit.

use console::Term;

use crate::error::CliError;

fn term() -> Result<Term, CliError> {
    let t = Term::stdout();
    if !t.is_term() {
        return Err(CliError::Failed(
            "This command needs a terminal to ask a question. \
             Pass the answer as an argument, or set the API key in the environment."
                .to_owned(),
        ));
    }
    Ok(t)
}

fn read_line(t: &Term) -> Result<String, CliError> {
    t.read_line()
        .map_err(|e| CliError::Failed(format!("Could not read the answer: {e}")))
}

/// Ask for a number in `1..=count`, repeating until one arrives.
///
/// A person who types `q` is told the range again rather than dropped out of the
/// flow they chose.
pub fn select(label: &str, count: usize) -> Result<usize, CliError> {
    let t = term()?;
    loop {
        t.write_str(&format!("{label}: "))
            .map_err(|e| CliError::Failed(e.to_string()))?;
        let answer = read_line(&t)?;
        match answer.trim().parse::<usize>() {
            Ok(n) if (1..=count).contains(&n) => return Ok(n),
            _ => {
                anstream::println!("Enter a number between 1 and {count}.");
            }
        }
    }
}

/// Ask for a secret, echoing nothing.
pub fn secret(label: &str) -> Result<String, CliError> {
    let t = term()?;
    t.write_str(&format!("{label}: "))
        .map_err(|e| CliError::Failed(e.to_string()))?;
    let value = t
        .read_secure_line()
        .map_err(|e| CliError::Failed(format!("Could not read the value: {e}")))?;
    if value.trim().is_empty() {
        return Err(CliError::Failed("No value was entered.".to_owned()));
    }
    Ok(value)
}
