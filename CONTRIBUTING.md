# How ideas become Venus features

Venus is started by **Anamorph Labs** and grows with the people who use it.
Ideas are welcome from anyone, written up by you or by your AI.

**The short version:** you suggest, we check, Anamorph Labs builds the good ones,
and you are thanked by name.

1. **Suggest.** Describe the idea to your AI (Claude, Codex or any other) and ask it
   to run `alvenus suggest "your idea"`. It writes the idea up with you (what, why,
   one example, the name to credit) and checks that nothing private is in it. Then it
   gives you a link to a filled-in form on GitHub. You read it and press Submit
   yourself: Venus never sends anything for you.
   No AI? Use the **Suggest a feature** form on the Issues tab directly.
2. **Add-ons.** New style packs and story recipes can be shared as add-ons: small
   data files, never code (see [alvenus/addons](alvenus/addons/README.md)). Use the
   **Share an add-on** form, or a pull request that only adds files under
   `alvenus/addons/`.
3. **Code is never added to Venus directly.** Pull requests go to a separate
   holding area (the `community` branch), never into the main code, even after a
   proposal is accepted. Every proposal is scanned automatically: the full test
   suite, a test render, three security scanners, a check for leaked passwords and
   keys, a check of every library and licence, and the add-on rules. The main code
   can only be changed by Anamorph Labs.
4. **We build it.** Anamorph Labs reviews each proposal. The good ones are built
   into Venus by the Venus team, cleanly and in its own style, even when the
   proposal came with code. Code you send helps us understand the idea; it is not
   copied in as it is.
5. **Thank you.** When your idea ships you get a thank-you on GitHub naming the
   version it is in, your name goes on the contributors list and on the Anamorph
   Labs site, and a thank-you email if you asked for one.

## Thank-you by email

The GitHub forms are public, so never put your email in them. If you would like a
thank-you email, send your GitHub name and the title of your suggestion to
creative@anamorphlabs.com. It is used for that note only.

## What makes a good suggestion

- One idea per suggestion. Say what Venus would do that it can't today.
- Say why it makes videos better, and for whom.
- Give one concrete example: the video, the moment, what a viewer would see.
- Nothing private: no footage, no keys, no paths from your computer.

## Rules for add-ons

- Data only: a JSON file in `alvenus/addons/styles/` or `alvenus/addons/recipes/`.
  No Python, no scripts, no downloads.
- Every value must be one Venus already knows (a look, a transition, a scene form).
  Venus checks each file and skips a bad one with a note: `alvenus suggest --addons`.
- `"by"` names you, for the credit. Your own work only, shared under the MIT licence.

## Support Venus

If Venus helps you, you can support Anamorph Labs with the **Sponsor** button on
this page. It is never required: ideas are the most valuable contribution.

Everyone taking part is expected to be kind and constructive. Security problems:
please report them privately, see [SECURITY.md](SECURITY.md).
