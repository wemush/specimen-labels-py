# WOLS CLI Demo
# Run with: vhs demo.tape

Output demo.gif

Set Shell "zsh"
Set FontFamily "FiraCode Nerd Font"
Set FontSize 15
Set Width 880
Set Height 600
Set Padding 24
Set Margin 20
Set MarginFill "#4A3728"
Set BorderRadius 10
Set LineHeight 1.3
Set TypingSpeed 40ms
Set CursorBlink false
Set Theme "Dracula"

# Clear and show version
Hide
Type "clear"
Enter
Show
Sleep 300ms

Hide

Type "🍄 WOLS - WeMush Open Labeling Standard"
Ctrl+C
Show
Sleep 800ms

Type "wols --version"
Enter
Sleep 1.2s

Type "wols --help"
Enter
Sleep 1.5s

# Create a specimen with human-readable output
Sleep 500ms
Hide
Type "━━━ Creating a specimen label ━━━"
Ctrl+C
Show
Sleep 600ms

Type "wols create --species 'Pleurotus ostreatus' --type SUBSTRATE --strain 'Blue Oyster' --stage COLONIZATION"
Enter
Sleep 2.5s

# Create specimen as JSON
Sleep 400ms
Hide
Type "clear"
Enter
Type "━━━ JSON output format ━━━"
Ctrl+C
Show
Sleep 600ms

Type "wols create --species 'Hericium erinaceus' --type CULTURE --strain 'Lions Mane' --json | head -18"
Enter
Sleep 2.5s

# Save to file and validate
Sleep 400ms
Hide
Type "━━━ Save and validate ━━━"
Ctrl+C
Show
Sleep 600ms

Type "wols create --species 'Ganoderma lucidum' --type SPAWN --strain 'Reishi' -o specimen.json"
Enter
Sleep 1.5s

Type "wols validate specimen.json"
Enter
Sleep 1.8s

# Generate QR code
Sleep 400ms
Type "━━━ Generate QR code ━━━"
Ctrl+C
Show
Sleep 600ms

Type "wols qr specimen.json -o label.png --size 300"
Enter
Sleep 2s

# Show files created
Type "ls -lh specimen.json label.png"
Enter
Sleep 1.5s

# Done
Sleep 300ms
Hide
Type "🍄 Happy cultivating!"
Ctrl+C
Show
Sleep 2s
