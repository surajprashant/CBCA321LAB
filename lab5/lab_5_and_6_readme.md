# Cgroups Lab Implementation Report

##  Environment Setup

Because this project was completed on an Apple Mac computer, we could not use the native operating system. Cgroups are an exclusive feature of the Linux kernel. To solve this problem, we created an isolated Linux environment using Docker.

We launched an Ubuntu container with elevated root privileges and host namespace permissions. This allowed our program to communicate directly with the core system resources.

## Program Workflow

The C program successfully performs the following actions without relying on basic shell scripts:

1. Creates a brand new control group directory called lab56.

2. Creates a child process and assigns it to this new group.

3. Applies a strict CPU limit of 20 percent.

4. Applies a maximum process limit of 1.

5. Inspects and prints the new configuration settings to the screen.

## Testing and Verification

The program tests the applied limits automatically. First, the child process attempts to replicate itself. The kernel blocks this action immediately, proving that the maximum process limit works perfectly.

Next, the child process enters an endless loop to consume as much processing power as possible. By opening a second terminal window and using the top command, we successfully verified that the system throttled the program to stay exactly at the 20 percent limit.

## Troubleshooting Summary

We encountered and resolved a few technical hurdles during setup:

* Missing Source File: The initial container lacked the text file. We installed the nano editor to write the code directly inside the container.

* Missing C Libraries: The compiler threw an error because the lightweight container did not have standard C headers. We resolved this by installing the libc6 dev package.

* Permission Errors: The system blocked our program from changing resource limits due to namespace isolation. We fixed this by restarting the container with a special flag to share the host namespace.