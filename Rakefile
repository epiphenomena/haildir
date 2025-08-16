require 'rake'
require 'rake/clean'

# Directories
TEST_MAILDIR = 'test/maildir'
TEST_OUTPUT = 'test/output'

# Clean task
CLEAN.include(TEST_OUTPUT)

# Task to run the haildir tool on test data
desc "Run haildir on test Maildir"
task :test do
  sh "rm -rf #{TEST_OUTPUT}"
  sh "uv run haildir #{TEST_MAILDIR} #{TEST_OUTPUT}"
  puts "Test output generated in #{TEST_OUTPUT}"
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