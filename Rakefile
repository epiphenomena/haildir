require 'rake'
require 'rake/clean'

# Directories
TEST_MAILDIR = 'test/maildir'
TEST_OUTPUT = 'test/output'
SEARCH_MAILDIR = 'test/search_maildir'
SEARCH_OUTPUT = 'test/search_output'

# Clean task
CLEAN.include(TEST_OUTPUT)
CLEAN.include(SEARCH_MAILDIR)
CLEAN.include(SEARCH_OUTPUT)

# Task to run the haildir tool on test data
desc "Run haildir on test Maildir"
task :test do
  sh "uv run haildir --rebuild #{TEST_MAILDIR} #{TEST_OUTPUT}"
  puts "Test output generated in #{TEST_OUTPUT}"
end

# Task to check the search against an index big enough to exercise it
desc "Check the search functions against a generated index"
task :search_test do
  sh "uv run python test/gen_search_maildir.py #{SEARCH_MAILDIR}"
  sh "uv run haildir --rebuild #{SEARCH_MAILDIR} #{SEARCH_OUTPUT}"
  sh "node test/search_test.js #{SEARCH_OUTPUT}"
end

# Task to run a simple HTTP server for development
desc "Run a simple HTTP server for the test output"
task :serve do
  Dir.chdir(TEST_OUTPUT) do
    sh "python3 -m http.server 8000"
  end
end

# Task to run tests and then serve
desc "Run tests and then serve the output"
task :test_and_serve => [:test, :serve]

# Default task
task :default => :test