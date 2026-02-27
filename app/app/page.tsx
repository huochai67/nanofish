"use client";

import { Button, Card, CardContent, CardHeader } from "@heroui/react";

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="flex flex-col items-center gap-3 bg-gradient-to-r from-blue-500 to-indigo-600 text-white py-8">
          <h1 className="text-4xl font-bold">Hello World</h1>
          <p className="text-lg opacity-90">Welcome to HeroUI</p>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-6 py-8">
          <p className="text-center text-gray-600 dark:text-gray-300 text-lg">
            You successfully created a page using HeroUI components!
          </p>
          <div className="flex gap-3">
            <Button variant='primary' className="font-semibold">
              Get Started
            </Button>
            <Button variant='outline' className="font-semibold">
              Learn More
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
